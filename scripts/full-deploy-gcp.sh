#!/usr/bin/env bash
# Full initial deploy: infra -> build backend -> deploy backend -> build frontend -> deploy frontend -> (optional) wait for health.
# Goal: set PROJECT_ID (and optionally REGION), run this, get a working deployment.
# Requires: terraform, gcloud, docker. Run from repository root.
#
# Resume: Terraform and this script are idempotent. If a step fails, fix the issue then re-run
# the same command; Terraform will skip resources that already exist, and you can re-run from
# the step that failed (e.g. re-run full script, or run deploy-gcp.sh after building images).
#
# Usage:
#   export PROJECT_ID=my-gcp-project
#   ./scripts/full-deploy-gcp.sh
#   ./scripts/full-deploy-gcp.sh -auto-approve
#   PROJECT_ID=my-project REGION=us-central1 ./scripts/full-deploy-gcp.sh
#   SKIP_HEALTH_WAIT=1 ./scripts/full-deploy-gcp.sh   # skip waiting for /api/health

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TERRAFORM_DIR="${TERRAFORM_DIR:-terraform/gcp}"
TF_DIR="${REPO_ROOT}/${TERRAFORM_DIR}"
REGION="${REGION:-us-central1}"
REPO_ID="${REPO_ID:-pr-agent-dash-repo}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SKIP_HEALTH_WAIT="${SKIP_HEALTH_WAIT:-0}"
OVERWRITE_CONFIG_SEED="${OVERWRITE_CONFIG_SEED:-0}"

# Project ID: from env or from terraform.tfvars
if [ -n "$TF_VAR_project_id" ]; then
  PROJECT_ID="${TF_VAR_project_id}"
fi
if [ -z "$PROJECT_ID" ] && [ -f "${TF_DIR}/terraform.tfvars" ]; then
  PROJECT_ID=$(grep -E '^\s*project_id\s*=' "${TF_DIR}/terraform.tfvars" | sed -E 's/.*=\s*"([^"]+)".*/\1/' | head -1)
fi
if [ -z "$PROJECT_ID" ]; then
  echo "Set PROJECT_ID (e.g. export PROJECT_ID=my-gcp-project) or set project_id in ${TF_DIR}/terraform.tfvars" >&2
  exit 1
fi

REGISTRY="${REGION}-docker.pkg.dev"
IMAGE_BASE="${REGISTRY}/${PROJECT_ID}/${REPO_ID}"
BACKEND_IMAGE="${IMAGE_BASE}/backend:${IMAGE_TAG}"
FRONTEND_IMAGE="${IMAGE_BASE}/frontend:${IMAGE_TAG}"
PR_AGENT_IMAGE="${IMAGE_BASE}/pr-agent:${IMAGE_TAG}"

APPLY_OPTS=("$@")
if [[ " ${APPLY_OPTS[*]} " != *" -auto-approve "* ]]; then
  echo "Tip: use -auto-approve to skip Terraform prompts."
fi

cd "$TF_DIR"

echo "=== 1/7 Terraform init ==="
terraform init -input=false

echo "=== 2/7 Terraform apply (infra only; no Cloud Run until images set) ==="
terraform apply -input=false "${APPLY_OPTS[@]}"

echo "=== 3/8 Build and push PR-Agent runner image ==="
cd "$REPO_ROOT"
if [ ! -f .dockerignore.pr-agent ]; then
  echo "Error: .dockerignore.pr-agent not found. PR-Agent image would be missing pr_agent/ code."
  exit 1
fi
_restore_dockerignore() { [ -f .dockerignore.bak ] && mv .dockerignore.bak .dockerignore || true; }
[ -f .dockerignore ] && cp .dockerignore .dockerignore.bak
cp .dockerignore.pr-agent .dockerignore
trap '_restore_dockerignore' EXIT
docker build -f Dockerfile.github_action -t "$PR_AGENT_IMAGE" .
docker push "$PR_AGENT_IMAGE"
_restore_dockerignore
trap - EXIT

echo "=== 4/8 Build and push backend ==="
cd "$REPO_ROOT"
gcloud auth configure-docker "${REGISTRY}" --quiet
docker build -f dashboard/backend/Dockerfile -t "$BACKEND_IMAGE" .
docker push "$BACKEND_IMAGE"

echo "=== 5/8 Deploy backend (Cloud Run) ==="
cd "$TF_DIR"
terraform apply -input=false \
  -var="backend_image=${BACKEND_IMAGE}" \
  -var="pr_agent_runner_image=${PR_AGENT_IMAGE}" \
  "${APPLY_OPTS[@]}"

BACKEND_URL=$(terraform output -raw backend_url 2>/dev/null || true)
if [ -z "$BACKEND_URL" ] || [ "$BACKEND_URL" = "null" ]; then
  echo "Error: backend_url output missing after deploy." >&2
  exit 1
fi
WS_URL="${BACKEND_URL/https/wss}"
WS_URL="${WS_URL%/}/ws"

echo "=== 6/8 Build and push frontend (REACT_APP_API_URL=$BACKEND_URL) ==="
cd "$REPO_ROOT"
docker build -f dashboard/frontend/Dockerfile \
  --build-arg "REACT_APP_API_URL=$BACKEND_URL" \
  --build-arg "REACT_APP_WS_URL=$WS_URL" \
  -t "$FRONTEND_IMAGE" .
docker push "$FRONTEND_IMAGE"

echo "=== 7/8 Deploy frontend and set backend/frontend URLs (CORS, links) ==="
cd "$TF_DIR"
FRONTEND_URL_PLACEHOLDER=""
terraform apply -input=false \
  -var="backend_image=${BACKEND_IMAGE}" \
  -var="frontend_image=${FRONTEND_IMAGE}" \
  -var="pr_agent_runner_image=${PR_AGENT_IMAGE}" \
  -var="backend_base_url=${BACKEND_URL}" \
  -var="frontend_base_url=${FRONTEND_URL_PLACEHOLDER}" \
  "${APPLY_OPTS[@]}"

FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || true)
if [ -n "$FRONTEND_URL" ] && [ "$FRONTEND_URL" != "null" ]; then
  echo "=== 6b/7 Second apply to set frontend_base_url ==="
  terraform apply -input=false \
    -var="backend_image=${BACKEND_IMAGE}" \
    -var="frontend_image=${FRONTEND_IMAGE}" \
    -var="pr_agent_runner_image=${PR_AGENT_IMAGE}" \
    -var="backend_base_url=${BACKEND_URL}" \
    -var="frontend_base_url=${FRONTEND_URL}" \
    "${APPLY_OPTS[@]}"
fi

if [ "$SKIP_HEALTH_WAIT" != "1" ] && [ -n "$BACKEND_URL" ]; then
  echo "=== 8/8 Waiting for backend health (up to 120s) ==="
  for i in $(seq 1 24); do
    if curl -sf "${BACKEND_URL}/api/health" >/dev/null 2>&1; then
      echo "Backend healthy."
      break
    fi
    echo "  Attempt $i/24..."
    sleep 5
  done
  if ! curl -sf "${BACKEND_URL}/api/health" >/dev/null 2>&1; then
    echo "Warning: backend health check did not succeed; deployment may still be rolling out."
  fi
else
  echo "=== 8/8 Skipping health wait (set SKIP_HEALTH_WAIT=0 to wait) ==="
fi

echo ""
echo "=== Deployment complete ==="
echo "Backend:  $BACKEND_URL"
echo "Frontend: ${FRONTEND_URL:-n/a}"
echo "PR-Agent image: ${PR_AGENT_IMAGE}"
if [ "$OVERWRITE_CONFIG_SEED" = "1" ]; then
  CONFIG_BUCKET=$(terraform output -raw config_bucket 2>/dev/null || true)
  if [ -n "$CONFIG_BUCKET" ] && [ "$CONFIG_BUCKET" != "null" ]; then
    echo "Overwriting GCS config seed files (requested by OVERWRITE_CONFIG_SEED=1)..."
    gcloud storage cp "${TF_DIR}/config-seed/configuration.toml" "gs://${CONFIG_BUCKET}/pr-agent-config/configuration.toml"
    gcloud storage cp "${TF_DIR}/config-seed/secrets.toml" "gs://${CONFIG_BUCKET}/pr-agent-config/secrets.toml"
  else
    echo "Warning: OVERWRITE_CONFIG_SEED=1 was set, but config_bucket output is empty."
  fi
fi
echo ""
API_KEY=$(terraform output -raw dashboard_api_key 2>/dev/null || true)
if [ -n "$API_KEY" ] && [ "$API_KEY" != "null" ]; then
  echo "DASHBOARD_API_KEY (set in PR-Agent / pipelines): $API_KEY"
  echo "(Store securely; e.g. GitHub Actions secret or Azure DevOps variable.)"
fi
CONFIG_BUCKET=$(terraform output -raw config_bucket 2>/dev/null || true)
if [ -n "$CONFIG_BUCKET" ] && [ "$CONFIG_BUCKET" != "null" ]; then
  echo "Config: PR_AGENT_CONFIG_GCS_BUCKET=$CONFIG_BUCKET  PR_AGENT_CONFIG_GCS_PREFIX=pr-agent-config/"
fi
echo "Runner VMs: Use 'Provision runner VM' in the dashboard when adding a repo with a self-hosted runner connection."
