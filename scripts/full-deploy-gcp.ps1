# Full deploy from infra onward: build backend -> deploy backend -> build frontend -> deploy frontend -> optional health wait.
# Run from repository root. Requires: Docker Desktop running, terraform, gcloud.
# Infra must already exist (terraform apply has been run at least once).
#
# Usage:
#   .\scripts\full-deploy-gcp.ps1
#   .\scripts\full-deploy-gcp.ps1 -AutoApprove
#   .\scripts\full-deploy-gcp.ps1 -ProjectId pr-agent-test-deploy -WaitForHealth

param(
    [string]$ProjectId = "pr-agent-test-deploy",
    [string]$Region = "us-central1",
    [string]$RepoId = "pr-agent-dash-repo",
    [string]$ImageTag = "latest",
    [switch]$AutoApprove,
    [switch]$WaitForHealth,
    [switch]$OverwriteConfigSeed
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$TfDir = Join-Path $RepoRoot "terraform\gcp"

$Registry = "$Region-docker.pkg.dev"
$ImageBase = "$Registry/$ProjectId/$RepoId"
$BackendImage = "$ImageBase/backend:$ImageTag"
$FrontendImage = "$ImageBase/frontend:$ImageTag"
$PrAgentImage = "$ImageBase/pr-agent:$ImageTag"

Write-Host "=== Configuring Docker for Artifact Registry ==="
gcloud auth configure-docker "${Registry}" --quiet

Push-Location $RepoRoot
try {
    Write-Host "=== Building PR-Agent image: $PrAgentImage ==="
    $dockerignorePath = Join-Path $RepoRoot ".dockerignore"
    $dockerignoreBak = Join-Path $RepoRoot ".dockerignore.bak"
    $dockerignorePrAgent = Join-Path $RepoRoot ".dockerignore.pr-agent"
    if (-not (Test-Path $dockerignorePrAgent)) {
        throw ".dockerignore.pr-agent not found at $dockerignorePrAgent. PR-Agent image would be missing pr_agent/ code."
    }
    if (Test-Path $dockerignorePath) { Copy-Item $dockerignorePath $dockerignoreBak -Force }
    Copy-Item $dockerignorePrAgent $dockerignorePath -Force
    try {
        docker build -f Dockerfile.github_action -t $PrAgentImage .
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "=== Pushing PR-Agent image ==="
        docker push $PrAgentImage
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        if (Test-Path $dockerignoreBak) { Move-Item $dockerignoreBak $dockerignorePath -Force }
    }

    Write-Host "=== Building backend: $BackendImage ==="
    docker build -f dashboard/backend/Dockerfile -t $BackendImage .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "=== Pushing backend ==="
    docker push $BackendImage
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "=== Deploying backend (Cloud Run) ==="
    Push-Location $TfDir
    $applyOpts = @(
        "-input=false",
        "-var=backend_image=$BackendImage",
        "-var=pr_agent_runner_image=$PrAgentImage"
    )
    if ($AutoApprove) { $applyOpts += "-auto-approve" }
    terraform apply @applyOpts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $BackendUrl = terraform output -raw backend_url 2>$null
    if (-not $BackendUrl -or $BackendUrl -eq "null") {
        Write-Error "backend_url output missing after deploy."
    }
    $WsUrl = ($BackendUrl -replace '^https', 'wss' -replace '/$', '') + "/ws"

    Pop-Location
    Push-Location $RepoRoot

    Write-Host "=== Building frontend (REACT_APP_API_URL=$BackendUrl) ==="
    docker build -f dashboard/frontend/Dockerfile `
        --build-arg "REACT_APP_API_URL=$BackendUrl" `
        --build-arg "REACT_APP_WS_URL=$WsUrl" `
        -t $FrontendImage .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "=== Pushing frontend ==="
    docker push $FrontendImage
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "=== Deploying frontend and setting URLs (CORS) ==="
    Push-Location $TfDir
    $FrontendUrl = terraform output -raw frontend_url 2>$null
    if (-not $FrontendUrl -or $FrontendUrl -eq "null") { $FrontendUrl = "" }
    $applyOpts = @(
        "-input=false",
        "-var=backend_image=$BackendImage",
        "-var=frontend_image=$FrontendImage",
        "-var=pr_agent_runner_image=$PrAgentImage",
        "-var=backend_base_url=$BackendUrl",
        "-var=frontend_base_url=$FrontendUrl"
    )
    if ($AutoApprove) { $applyOpts += "-auto-approve" }
    terraform apply @applyOpts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $FrontendUrl = terraform output -raw frontend_url 2>$null
    if ($FrontendUrl -and $FrontendUrl -ne "null") {
        Write-Host "=== Second apply (frontend_base_url for CORS) ==="
        $secondApplyOpts = @(
            "-input=false",
            "-var=backend_image=$BackendImage",
            "-var=frontend_image=$FrontendImage",
            "-var=pr_agent_runner_image=$PrAgentImage",
            "-var=backend_base_url=$BackendUrl",
            "-var=frontend_base_url=$FrontendUrl"
        )
        if ($AutoApprove) { $secondApplyOpts += "-auto-approve" }
        terraform apply @secondApplyOpts
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    if ($WaitForHealth) {
        Write-Host "=== Waiting for backend health (up to 120s) ==="
        $attempt = 0
        $healthy = $false
        while ($attempt -lt 24) {
            try {
                $r = Invoke-WebRequest -Uri "$BackendUrl/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
                if ($r.StatusCode -eq 200) { Write-Host "Backend healthy."; $healthy = $true; break }
            } catch {}
            $attempt++; Write-Host "  Attempt $attempt/24..."; Start-Sleep -Seconds 5
        }
        if (-not $healthy) { Write-Host "Warning: health check did not succeed." }
    }

    Write-Host ""
    Write-Host "=== Deployment complete ==="
    Write-Host "Backend:  $BackendUrl"
    Write-Host "Frontend: $FrontendUrl"
    Write-Host "PR-Agent image: $PrAgentImage"
    if ($OverwriteConfigSeed) {
        $configBucket = terraform output -raw config_bucket 2>$null
        if ($configBucket -and $configBucket -ne "null") {
            Write-Host "Overwriting GCS config seed files (requested by -OverwriteConfigSeed)..."
            gcloud storage cp (Join-Path $TfDir "config-seed\configuration.toml") "gs://$configBucket/pr-agent-config/configuration.toml"
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            gcloud storage cp (Join-Path $TfDir "config-seed\secrets.toml") "gs://$configBucket/pr-agent-config/secrets.toml"
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } else {
            Write-Host "Warning: -OverwriteConfigSeed was set, but config_bucket output is empty."
        }
    }
    $ApiKey = terraform output -raw dashboard_api_key 2>$null
    if ($ApiKey -and $ApiKey -ne "null") {
        Write-Host ""
        Write-Host "DASHBOARD_API_KEY (set in PR-Agent / pipelines): $ApiKey"
    }
    $ConfigBucket = terraform output -raw config_bucket 2>$null
    if ($ConfigBucket -and $ConfigBucket -ne "null") {
        Write-Host "Config: PR_AGENT_CONFIG_GCS_BUCKET=$ConfigBucket  PR_AGENT_CONFIG_GCS_PREFIX=pr-agent-config/"
    }
}
finally {
    Pop-Location
}
