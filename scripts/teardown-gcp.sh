#!/usr/bin/env bash
# Teardown: destroy ALL resources created by the GCP deployment (Terraform).
# Leaves the project in a clean slate so you can run deploy again.
# Run from repository root. Requires: terraform, gcloud (for auth).
#
# Usage:
#   ./scripts/teardown-gcp.sh              # Prompts for confirmation
#   ./scripts/teardown-gcp.sh -auto-approve   # No prompt; destroy immediately
#   TERRAFORM_DIR=terraform/gcp ./scripts/teardown-gcp.sh
#
# What gets destroyed (everything Terraform created):
#   - VPC network, subnets, connector, Private Service Access peering
#   - Cloud SQL instance (PostgreSQL), database, user
#   - Secret Manager secrets (DATABASE_URL, DASHBOARD_CRON_SECRET)
#   - GCS config bucket and objects
#   - Artifact Registry repository
#   - Cloud Run services (backend, frontend)
#   - Cloud Scheduler job
#   - Runner VM (if enable_runner_vm was true)
#   - Enabled APIs are left enabled (no cost by themselves)

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TERRAFORM_DIR="${TERRAFORM_DIR:-terraform/gcp}"
TF_DIR="${REPO_ROOT}/${TERRAFORM_DIR}"

if [ ! -f "${TF_DIR}/main.tf" ]; then
  echo "Terraform dir not found: ${TF_DIR}" >&2
  exit 1
fi

echo ""
echo "=== PR-Agent Dashboard GCP TEARDOWN ==="
echo ""
echo "This will DESTROY all resources created by Terraform for this deployment:"
echo "  - VPC (network, subnets, connector, peering)"
echo "  - Cloud SQL (PostgreSQL instance, DB, user)"
echo "  - Secret Manager secrets"
echo "  - GCS config bucket and objects"
echo "  - Artifact Registry repo"
echo "  - Cloud Run (backend, frontend)"
echo "  - Cloud Scheduler job"
echo "  - Runner VM (if created)"
echo ""
echo "Your GCP project will be left in a clean slate. You can run deploy again afterward."
echo ""

# Check for -auto-approve in args
AUTO_APPROVE=""
for arg in "$@"; do
  if [ "$arg" = "-auto-approve" ]; then
    AUTO_APPROVE="-auto-approve"
    break
  fi
done

if [ -z "$AUTO_APPROVE" ]; then
  printf "Type 'yes' to proceed with teardown (or anything else to cancel): "
  read -r confirm
  if [ "$confirm" != "yes" ]; then
    echo "Teardown cancelled."
    exit 0
  fi
fi

cd "$TF_DIR"

echo "=== Terraform init (ensure state is available) ==="
terraform init -input=false

echo ""
echo "=== Terraform destroy (removing all resources) ==="
if ! terraform destroy -input=false "$@"; then
  echo ""
  echo "Destroy failed. Common causes:"
  echo "  - Cloud SQL: ensure deletion_protection = false in main.tf"
  echo "  - GCS bucket: ensure force_destroy = true on the config bucket"
  echo "  - Run 'terraform state list' to see what Terraform tracks, then fix or remove stuck resources"
  exit 1
fi

echo ""
echo "=== Teardown complete ==="
echo "Project is clean. Run ./scripts/full-deploy-gcp.ps1 or ./scripts/deploy-gcp.sh to deploy again."
echo ""
