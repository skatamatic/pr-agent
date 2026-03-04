# Deployment script tests

Tests for GCP deployment scripts (`deploy-gcp.*`, `build-push-gcp.*`) and Terraform validation.

**Run from repo root:**

```bash
pytest scripts/tests/test_gcp_scripts.py -v
```

**What is tested**

- **deploy-gcp.sh / deploy-gcp.ps1**: Exit with error when `TERRAFORM_DIR` (or `TerraformDir`) points to a directory that does not contain `main.tf`.
- **build-push-gcp.sh / build-push-gcp.ps1**: Exit with error when `PROJECT_ID` / `TF_VAR_project_id` (or `ProjectId`) are not set.
- **terraform/gcp/validate.sh** (Linux/macOS or WSL): `terraform init`, `validate`, and `fmt -check` succeed with a dummy `project_id` (no GCP access).
- **terraform/gcp/validate.ps1** (Windows or when pwsh/powershell available): Same as above.

**Windows:** PowerShell (`.ps1`) tests always run. Bash (`.sh`) tests run **via WSL** when WSL is installed; they are skipped if WSL is missing or if `bash` is not available in the default WSL distro (use e.g. Ubuntu WSL for full coverage). Terraform validate tests require `terraform` on PATH (Windows) or in WSL (for the `.sh` validate test).
