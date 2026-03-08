# Single script to re-deploy: PR-Agent image (for self-hosted runner VMs), dashboard backend, and dashboard frontend.
# Pushes all images to GCP Artifact Registry and runs Terraform to update Cloud Run and runner VM config.
#
# Prerequisites: Docker running, gcloud, terraform. Infra must already exist (run full-deploy-gcp once).
#
# Usage:
#   .\scripts\redeploy-gcp.ps1
#   .\scripts\redeploy-gcp.ps1 -AutoApprove -WaitForHealth
#   .\scripts\redeploy-gcp.ps1 -ProjectId pr-agent-test-deploy
# By default uses a unique image tag (deploy-<timestamp>) so Cloud Run gets new revisions. Use -ImageTag latest to reuse :latest.

param(
    [string]$ProjectId = "",
    [string]$Region = "us-central1",
    [string]$RepoId = "pr-agent-dash-repo",
    [string]$ImageTag = "",   # default: unique deploy-<timestamp> so Terraform updates Cloud Run
    [switch]$AutoApprove,
    [switch]$WaitForHealth,
    [switch]$SkipPrAgentImage
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$TfDir = Join-Path $RepoRoot "terraform\gcp"

# Resolve project ID and repo ID from env or tfvars
if (-not $ProjectId -and $env:TF_VAR_project_id) { $ProjectId = $env:TF_VAR_project_id }
if (-not $ProjectId -and $env:PROJECT_ID) { $ProjectId = $env:PROJECT_ID }
$tfvarsPath = Join-Path $TfDir "terraform.tfvars"
if (Test-Path $tfvarsPath) {
    $tfvars = Get-Content $tfvarsPath
    if (-not $ProjectId) {
        $line = $tfvars | Where-Object { $_ -match '^\s*project_id\s*=' } | Select-Object -First 1
        if ($line -match '"([^"]+)"') { $ProjectId = $Matches[1] }
    }
    # Repo ID must match Terraform: repository_id = "${prefix}-repo"
    if ($RepoId -eq "pr-agent-dash-repo") {
        $line = $tfvars | Where-Object { $_ -match '^\s*prefix\s*=' } | Select-Object -First 1
        if ($line -match '"([^"]+)"') { $RepoId = $Matches[1] + "-repo" }
    }
}
if (-not $ProjectId) {
    Write-Error "Set ProjectId (e.g. -ProjectId my-project) or PROJECT_ID / project_id in terraform.tfvars"
}

# Unique tag per deploy so Terraform sees a new image URL and updates Cloud Run (fixes frontend/backend not updating when using :latest)
if (-not $ImageTag) { $ImageTag = "deploy-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())" }
Write-Host "Image tag: $ImageTag"

$Registry = "$Region-docker.pkg.dev"
$ImageBase = "$Registry/$ProjectId/$RepoId"
$BackendImage = "$ImageBase/backend:$ImageTag"
$FrontendImage = "$ImageBase/frontend:$ImageTag"
$PrAgentImage = "$ImageBase/pr-agent:$ImageTag"

Write-Host "=== Configuring Docker for Artifact Registry ==="
gcloud auth configure-docker "${Registry}" --quiet

Push-Location $RepoRoot
try {
    # --- 1. PR-Agent image (for self-hosted runner VMs) ---
    if (-not $SkipPrAgentImage) {
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
    } else {
        Write-Host "=== Skipping PR-Agent image (use without -SkipPrAgentImage to include) ==="
        # Preserve current value so Terraform does not clear GCP_RUNNER_PR_AGENT_IMAGE
        Push-Location $TfDir
        $current = terraform output -raw pr_agent_runner_image 2>$null
        Pop-Location
        if ($current -and $current -ne "null") { $PrAgentImage = $current } else { $PrAgentImage = "" }
    }

    # --- 2. Dashboard backend ---
    Write-Host "=== Building backend: $BackendImage ==="
    docker build -f dashboard/backend/Dockerfile -t $BackendImage .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "=== Pushing backend ==="
    docker push $BackendImage
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "=== Getting current backend URL ==="
    Push-Location $TfDir
    $BackendUrl = terraform output -raw backend_url 2>$null
    if (-not $BackendUrl -or $BackendUrl -eq "null") {
        Write-Error "backend_url output missing; run full-deploy-gcp first."
    }
    $WsUrl = ($BackendUrl -replace '^https', 'wss' -replace '/$', '') + "/ws"
    Pop-Location
    Push-Location $RepoRoot

    # --- 3. Dashboard frontend ---
    Write-Host "=== Building frontend (REACT_APP_API_URL=$BackendUrl) ==="
    docker build -f dashboard/frontend/Dockerfile `
        --build-arg "REACT_APP_API_URL=$BackendUrl" `
        --build-arg "REACT_APP_WS_URL=$WsUrl" `
        -t $FrontendImage .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "=== Pushing frontend ==="
    docker push $FrontendImage
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # --- 4. Deploy frontend and set CORS (keep pr_agent_runner_image if we built it) ---
    Write-Host "=== Deploying frontend and setting URLs (CORS) ==="
    Push-Location $TfDir
    $FrontendUrl = terraform output -raw frontend_url 2>$null
    if (-not $FrontendUrl -or $FrontendUrl -eq "null") { $FrontendUrl = "" }
    $applyOpts = @(
        "-input=false",
        "-var=backend_image=$BackendImage",
        "-var=frontend_image=$FrontendImage",
        "-var=backend_base_url=$BackendUrl",
        "-var=frontend_base_url=$FrontendUrl"
    )
    if ($PrAgentImage) { $applyOpts += "-var=pr_agent_runner_image=$PrAgentImage" }
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
            "-var=backend_base_url=$BackendUrl",
            "-var=frontend_base_url=$FrontendUrl"
        )
        if ($PrAgentImage) { $secondApplyOpts += "-var=pr_agent_runner_image=$PrAgentImage" }
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
    Write-Host "=== Redeploy complete ==="
    Write-Host "Backend:   $BackendUrl"
    Write-Host "Frontend:  $FrontendUrl"
    if ($PrAgentImage) {
        Write-Host "PR-Agent:  $PrAgentImage (used by new self-hosted runner VMs)"
    }
    $ApiKey = terraform output -raw dashboard_api_key 2>$null
    if ($ApiKey -and $ApiKey -ne "null") {
        Write-Host ""
        Write-Host "DASHBOARD_API_KEY: $ApiKey"
    }
}
finally {
    Pop-Location
}
