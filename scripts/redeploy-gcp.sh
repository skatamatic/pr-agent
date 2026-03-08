#!/usr/bin/env bash
# Single script to re-deploy: PR-Agent image (for self-hosted runner VMs), dashboard backend, and dashboard frontend.
# Pushes all images to GCP Artifact Registry and runs Terraform to update Cloud Run and runner VM config.
#
# Prerequisites: Docker, gcloud, terraform. Infra must already exist (run full-deploy-gcp.sh once).
#
# Usage:
#   ./scripts/redeploy-gcp.sh
#   ./scripts/redeploy-gcp.sh -auto-approve
#   PROJECT_ID=my-project ./scripts/redeploy-gcp.sh
#   SKIP_PR_AGENT_IMAGE=1 ./scripts/redeploy-gcp.sh   # skip building PR-Agent image
# By default uses a unique image tag (deploy-<timestamp>) so Cloud Run gets new revisions. Set IMAGE_TAG=latest to reuse :latest.

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform/gcp"
REGION="${REGION:-us-central1}"
REPO_ID="${REPO_ID:-pr-agent-dash-repo}"
# Unique tag per deploy so Terraform sees a new image URL and updates Cloud Run (fixes frontend/backend not updating when using :latest)
IMAGE_TAG="${IMAGE_TAG:-deploy-$(date +%s)}"
SKIP_PR_AGENT_IMAGE="${SKIP_PR_AGENT_IMAGE:-0}"
echo "Image tag: $IMAGE_TAG"

# Project ID and repo ID from env or tfvars
if [ -n "$TF_VAR_project_id" ]; then PROJECT_ID="$TF_VAR_project_id"; fi
if [ -z "$PROJECT_ID" ] && [ -f "${TF_DIR}/terraform.tfvars" ]; then
  PROJECT_ID=$(grep -E '^\s*project_id\s*=' "${TF_DIR}/terraform.tfvars" | sed -E 's/.*=\s*"([^"]+)".*/\1/' | head -1)
fi
if [ -z "$PROJECT_ID" ]; then
  echo "Set PROJECT_ID (e.g. export PROJECT_ID=my-project) or project_id in ${TF_DIR}/terraform.tfvars" >&2
  exit 1
fi
# Repo ID must match Terraform: repository_id = "${prefix}-repo"
if [ "$REPO_ID" = "pr-agent-dash-repo" ] && [ -f "${TF_DIR}/terraform.tfvars" ]; then
  PREFIX=$(grep -E '^\s*prefix\s*=' "${TF_DIR}/terraform.tfvars" | sed -E 's/.*=\s*"([^"]+)".*/\1/' | head -1)
  [ -n "$PREFIX" ] && REPO_ID="${PREFIX}-repo"
fi

REGISTRY="${REGION}-docker.pkg.dev"
IMAGE_BASE="${REGISTRY}/${PROJECT_ID}/${REPO_ID}"
BACKEND_IMAGE="${IMAGE_BASE}/backend:${IMAGE_TAG}"
FRONTEND_IMAGE="${IMAGE_BASE}/frontend:${IMAGE_TAG}"
PR_AGENT_IMAGE="${IMAGE_BASE}/pr-agent:${IMAGE_TAG}"

APPLY_OPTS=("$@")
[[ " ${APPLY_OPTS[*]} " != *" -auto-approve "* ]] && echo "Tip: use -auto-approve to skip Terraform prompts."

cd "$REPO_ROOT"

echo "=== Configuring Docker for Artifact Registry ==="
gcloud auth configure-docker "${REGISTRY}" --quiet

# --- 1. PR-Agent image (for self-hosted runner VMs) ---
if [ "$SKIP_PR_AGENT_IMAGE" != "1" ]; then
  echo "=== Building PR-Agent image: $PR_AGENT_IMAGE ==="
  if [ ! -f .dockerignore.pr-agent ]; then
    echo "Error: .dockerignore.pr-agent not found. PR-Agent image would be missing pr_agent/ code."
    exit 1
  fi
  _restore_dockerignore() { [ -f .dockerignore.bak ] && mv .dockerignore.bak .dockerignore || true; }
  [ -f .dockerignore ] && cp .dockerignore .dockerignore.bak
  cp .dockerignore.pr-agent .dockerignore
  trap '_restore_dockerignore' EXIT
  docker build -f Dockerfile.github_action -t "$PR_AGENT_IMAGE" .
  echo "=== Pushing PR-Agent image ==="
  docker push "$PR_AGENT_IMAGE"
  _restore_dockerignore
  trap - EXIT
else
  echo "=== Skipping PR-Agent image (set SKIP_PR_AGENT_IMAGE=0 to include) ==="
  PR_AGENT_IMAGE=$(cd "$TF_DIR" && terraform output -raw pr_agent_runner_image 2>/dev/null || true)
  [ "$PR_AGENT_IMAGE" = "null" ] && PR_AGENT_IMAGE=""
fi

# --- 2. Dashboard backend ---
echo "=== Building backend: $BACKEND_IMAGE ==="
docker build -f dashboard/backend/Dockerfile -t "$BACKEND_IMAGE" .
echo "=== Pushing backend ==="
docker push "$BACKEND_IMAGE"

echo "=== Getting current backend URL ==="
cd "$TF_DIR"
BACKEND_URL=$(terraform output -raw backend_url 2>/dev/null || true)
[ -z "$BACKEND_URL" ] || [ "$BACKEND_URL" = "null" ] && echo "Error: backend_url missing; run full-deploy-gcp first." >&2 && exit 1
WS_URL="${BACKEND_URL/https/wss}"
WS_URL="${WS_URL%/}/ws"

# --- 3. Dashboard frontend ---
cd "$REPO_ROOT"
echo "=== Building frontend (REACT_APP_API_URL=$BACKEND_URL) ==="
docker build -f dashboard/frontend/Dockerfile \
  --build-arg "REACT_APP_API_URL=$BACKEND_URL" \
  --build-arg "REACT_APP_WS_URL=$WS_URL" \
  -t "$FRONTEND_IMAGE" .
echo "=== Pushing frontend ==="
docker push "$FRONTEND_IMAGE"

# --- 4. Deploy frontend and CORS ---
echo "=== Deploying frontend and setting URLs (CORS) ==="
cd "$TF_DIR"
FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || true)
[ -z "$FRONTEND_URL" ] || [ "$FRONTEND_URL" = "null" ] && FRONTEND_URL=""
TF_VARS=(
  -input=false
  -var="backend_image=${BACKEND_IMAGE}"
  -var="frontend_image=${FRONTEND_IMAGE}"
  -var="backend_base_url=${BACKEND_URL}"
  -var="frontend_base_url=${FRONTEND_URL}"
)
[ -n "$PR_AGENT_IMAGE" ] && TF_VARS+=(-var="pr_agent_runner_image=${PR_AGENT_IMAGE}")
terraform apply "${TF_VARS[@]}" "${APPLY_OPTS[@]}"

FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || true)
if [ -n "$FRONTEND_URL" ] && [ "$FRONTEND_URL" != "null" ]; then
  echo "=== Second apply (frontend_base_url for CORS) ==="
  TF_VARS=(
    -input=false
    -var="backend_image=${BACKEND_IMAGE}"
    -var="frontend_image=${FRONTEND_IMAGE}"
    -var="backend_base_url=${BACKEND_URL}"
    -var="frontend_base_url=${FRONTEND_URL}"
  )
  [ -n "$PR_AGENT_IMAGE" ] && TF_VARS+=(-var="pr_agent_runner_image=${PR_AGENT_IMAGE}")
  terraform apply "${TF_VARS[@]}" "${APPLY_OPTS[@]}"
fi

echo ""
echo "=== Redeploy complete ==="
echo "Backend:   $BACKEND_URL"
echo "Frontend:  ${FRONTEND_URL:-n/a}"
[ -n "$PR_AGENT_IMAGE" ] && echo "PR-Agent:  $PR_AGENT_IMAGE (used by new self-hosted runner VMs)"
API_KEY=$(terraform output -raw dashboard_api_key 2>/dev/null || true)
[ -n "$API_KEY" ] && [ "$API_KEY" != "null" ] && echo "" && echo "DASHBOARD_API_KEY: $API_KEY"
