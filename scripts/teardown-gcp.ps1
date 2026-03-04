# Teardown: destroy ALL resources created by the GCP deployment (Terraform).
# Leaves the project in a clean slate so you can run deploy again.
# Run from repository root. Requires: terraform, gcloud (for auth).
#
# Usage:
#   .\scripts\teardown-gcp.ps1              # Prompts for confirmation
#   .\scripts\teardown-gcp.ps1 -Force        # No prompt; destroy immediately
#   .\scripts\teardown-gcp.ps1 -TerraformDir "terraform/gcp"

param(
    [switch]$Force,
    [string]$TerraformDir = "terraform/gcp"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$TfDir = Join-Path $RepoRoot $TerraformDir
if (-not (Test-Path (Join-Path $TfDir "main.tf"))) {
    Write-Error "Terraform dir not found: $TfDir"
}

Write-Host ""
Write-Host "=== PR-Agent Dashboard GCP TEARDOWN ===" -ForegroundColor Yellow
Write-Host ""
Write-Host "This will DESTROY all resources created by Terraform for this deployment:"
Write-Host "  - VPC (network, subnets, connector, peering)"
Write-Host "  - Cloud SQL (PostgreSQL instance, DB, user)"
Write-Host "  - Secret Manager secrets"
Write-Host "  - GCS config bucket and objects"
Write-Host "  - Artifact Registry repo"
Write-Host "  - Cloud Run (backend, frontend)"
Write-Host "  - Cloud Scheduler job"
Write-Host "  - Runner VM (if created)"
Write-Host ""
Write-Host "Your GCP project will be left in a clean slate. You can run deploy again afterward." -ForegroundColor Cyan
Write-Host ""

if (-not $Force) {
    $confirm = Read-Host "Type yes to proceed with teardown (or anything else to cancel)"
    if ($confirm -ne "yes") {
        Write-Host "Teardown cancelled."
        exit 0
    }
}

Push-Location $TfDir
try {
    Write-Host "=== Terraform init (ensure state is available) ==="
    terraform init -input=false
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "=== Terraform destroy (removing all resources) ===" -ForegroundColor Yellow
    $destroyOpts = @("-input=false")
    if ($Force) { $destroyOpts += "-auto-approve" }
    terraform destroy @destroyOpts
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Destroy failed. Common causes:" -ForegroundColor Red
        Write-Host "  - Cloud SQL: ensure deletion_protection = false in main.tf"
        Write-Host "  - GCS bucket: ensure force_destroy = true on the config bucket"
        Write-Host "  - Run terraform state list to see what Terraform tracks, then fix or remove stuck resources"
        exit $LASTEXITCODE
    }

    Write-Host ""
    Write-Host "=== Teardown complete ===" -ForegroundColor Green
    Write-Host "Project is clean. Run .\scripts\full-deploy-gcp.ps1 or .\scripts\deploy-gcp.ps1 to deploy again."
    Write-Host ""
}
finally {
    Pop-Location
}
