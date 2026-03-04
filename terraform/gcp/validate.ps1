# Run Terraform init (no backend), validate, and fmt check.
# No GCP access needed. From repo root: .\terraform\gcp\validate.ps1
# Or from this dir: .\validate.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=== terraform init (backend=false) ==="
terraform init -backend=false -input=false
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== terraform validate ==="
terraform validate -var="project_id=test-project-for-validate"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== terraform fmt -check ==="
terraform fmt -check -recursive -diff
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Terraform validation passed."
