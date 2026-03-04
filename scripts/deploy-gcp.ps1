# One-command deploy: apply Terraform, then re-apply with backend/frontend URLs from outputs
# so the dashboard backend gets correct DASHBOARD_BACKEND_BASE_URL and DASHBOARD_CORS_ORIGINS.
# Run from repository root. Requires: terraform, gcloud (for auth).
# Windows: run this .ps1 natively (recommended). Linux/macOS: use deploy-gcp.sh or this script with pwsh.
#
# Usage:
#   .\scripts\deploy-gcp.ps1
#   .\scripts\deploy-gcp.ps1 -AutoApprove
#   .\scripts\deploy-gcp.ps1 -TerraformDir "terraform/gcp"

param(
    [switch]$AutoApprove,
    [string]$TerraformDir = "terraform/gcp",
    [switch]$WaitForHealth   # After apply, wait for backend /api/health (up to 120s)
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$TfDir = Join-Path $RepoRoot $TerraformDir
if (-not (Test-Path (Join-Path $TfDir "main.tf"))) {
    Write-Error "Terraform dir not found: $TfDir"
}

Push-Location $TfDir
try {
    $applyOpts = @()
    if ($AutoApprove) { $applyOpts = @("-auto-approve") }

    Write-Host "=== First apply (infra + Cloud Run) ==="
    terraform apply @applyOpts
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $backendUrl = (terraform output -raw backend_url 2>$null)
    $frontendUrl = (terraform output -raw frontend_url 2>$null)
    if ($frontendUrl -eq "null" -or -not $frontendUrl) { $frontendUrl = "" }

    if ($backendUrl -and $backendUrl -ne "null") {
        Write-Host "=== Second apply (inject backend/frontend URLs for CORS and links) ==="
        $varOpts = @(
            "-var=backend_base_url=$backendUrl",
            "-var=frontend_base_url=$frontendUrl"
        )
        if ($AutoApprove) { $varOpts += "-auto-approve" }
        terraform apply @varOpts
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "Done. Backend and frontend URLs are set."

        if ($WaitForHealth) {
            Write-Host "=== Waiting for backend health (up to 120s) ==="
            $maxAttempts = 24
            $attempt = 0
            $healthy = $false
            while ($attempt -lt $maxAttempts) {
                try {
                    $r = Invoke-WebRequest -Uri "$backendUrl/api/health" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
                    if ($r.StatusCode -eq 200) { Write-Host "Backend healthy."; $healthy = $true; break }
                } catch {}
                $attempt++; Write-Host "  Attempt $attempt/$maxAttempts..."; Start-Sleep -Seconds 5
            }
            if (-not $healthy) { Write-Host "Warning: health check did not succeed; deployment may still be rolling out." }
        }
    }
    else {
        Write-Host "Backend URL not yet available (set backend_image and frontend_image, then apply again)."
    }

    $configBucket = (terraform output -raw config_bucket 2>$null)
    $configPrefix = (terraform output -raw config_prefix 2>$null)
    if ($configBucket -and $configBucket -ne "null") {
        Write-Host ""
        Write-Host "=== Shared config (GCS) ==="
        Write-Host "Dashboard backend uses GCS for config automatically (PR_AGENT_CONFIG_GCS_BUCKET/PREFIX set by Terraform)."
        Write-Host "For PR-Agent (pipeline, Cloud Run job, or VM), set the same env so it uses dashboard-edited config:"
        Write-Host "  PR_AGENT_CONFIG_GCS_BUCKET=$configBucket"
        Write-Host "  PR_AGENT_CONFIG_GCS_PREFIX=$configPrefix"
    }

    $apiKey = (terraform output -raw dashboard_api_key 2>$null)
    if ($apiKey -and $apiKey -ne "null") {
        Write-Host ""
        Write-Host "=== DASHBOARD_API_KEY (set in PR-Agent / pipelines so they can post jobs and logs) ==="
        Write-Host "Terraform generated this key and injected it into the backend. Set it in PR-Agent env or pipeline secrets:"
        Write-Host "  DASHBOARD_API_KEY=$apiKey"
        Write-Host "(Store securely; e.g. GitHub Actions secret or Azure DevOps variable.)"
    }

    Write-Host ""
    Write-Host "=== Runner VMs ==="
    Write-Host "GCP_RUNNER_* are set by Terraform; use 'Provision runner VM' in the dashboard when adding a repo with a self-hosted runner connection."
}
finally {
    Pop-Location
}
