# Build and push PR-Agent Dashboard images to GCP Artifact Registry.
# Run from the repository root. Requires: gcloud, Docker (Docker Desktop on Windows is fine).
# Windows: run this .ps1 natively (recommended). Linux/macOS: use build-push-gcp.sh or this script with pwsh.
#
# Usage:
#   .\scripts\build-push-gcp.ps1
#   .\scripts\build-push-gcp.ps1 -ProjectId my-project -Region us-central1 -BackendUrl "https://..."

param(
    [string]$ProjectId = $env:TF_VAR_project_id,
    [string]$Region = $env:TF_VAR_region,
    [string]$RepoId = "pr-agent-dash-repo",
    [string]$BackendUrl = "",  # Set after first deploy; used for frontend REACT_APP_API_URL / REACT_APP_WS_URL
    [string]$ImageTag = "latest",
    [switch]$BackendOnly,   # Build and push only backend (for full-deploy flow)
    [switch]$FrontendOnly  # Build and push only frontend (requires -BackendUrl)
)

$ErrorActionPreference = "Stop"

if (-not $ProjectId) {
    Write-Error "Set ProjectId (e.g. -ProjectId my-gcp-project) or TF_VAR_project_id"
}
if (-not $Region) {
    $Region = "us-central1"
}

$Registry = "${Region}-docker.pkg.dev"
$ImageBase = "${Registry}/${ProjectId}/${RepoId}"

Write-Host "Configuring Docker for Artifact Registry..."
gcloud auth configure-docker "${Registry}" --quiet

$RepoRoot = $PSScriptRoot + "\.."
Push-Location $RepoRoot

try {
    $BackendImage = "${ImageBase}/backend:${ImageTag}"
    $FrontendImage = "${ImageBase}/frontend:${ImageTag}"

    if (-not $FrontendOnly) {
        Write-Host "Building backend: $BackendImage"
        docker build -f dashboard/backend/Dockerfile -t $BackendImage .
        Write-Host "Pushing backend..."
        docker push $BackendImage
    }

    if (-not $BackendOnly) {
        if (-not $BackendUrl) {
            Write-Warning "BackendUrl not set. Frontend will be built with placeholder; rebuild after backend is deployed and set -BackendUrl."
            $BackendUrl = "https://BACKEND-URL.run.app"
        }
        $WsUrl = ($BackendUrl -replace '^https', 'wss' -replace '/$', '') + "/ws"
        Write-Host "Building frontend with REACT_APP_API_URL=$BackendUrl REACT_APP_WS_URL=$WsUrl"
        docker build -f dashboard/frontend/Dockerfile `
            --build-arg "REACT_APP_API_URL=$BackendUrl" `
            --build-arg "REACT_APP_WS_URL=$WsUrl" `
            -t $FrontendImage .
        Write-Host "Pushing frontend..."
        docker push $FrontendImage
    }

    Write-Host ""
    Write-Host "Done. Add to terraform.tfvars and run 'terraform apply':"
    if (-not $FrontendOnly) { Write-Host "  backend_image  = `"$BackendImage`"" }
    if (-not $BackendOnly) { Write-Host "  frontend_image = `"$FrontendImage`"" }
}
finally {
    Pop-Location
}
