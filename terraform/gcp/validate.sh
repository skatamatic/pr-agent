#!/usr/bin/env bash
# Run Terraform init (no backend), validate, and fmt check.
# No GCP access needed. Use from repo root: ./terraform/gcp/validate.sh
# Or from this dir: ./validate.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== terraform init (backend=false) ==="
terraform init -backend=false -input=false

echo "=== terraform validate ==="
terraform validate -var="project_id=test-project-for-validate"

echo "=== terraform fmt -check ==="
terraform fmt -check -recursive -diff

echo "Terraform validation passed."
