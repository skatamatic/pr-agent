#!/usr/bin/env bash
# Build and push PR-Agent Dashboard images to GCP Artifact Registry.
# Run from the repository root. Requires: gcloud, Docker, and Terraform outputs (or set vars below).
#
# Usage:
#   ./scripts/build-push-gcp.sh
#   PROJECT_ID=my-project REGION=us-central1 BACKEND_URL=https://xxx.run.app ./scripts/build-push-gcp.sh

set -e

PROJECT_ID="${TF_VAR_project_id:-$PROJECT_ID}"
REGION="${TF_VAR_region:-${REGION:-us-central1}}"
REPO_ID="${REPO_ID:-pr-agent-dash-repo}"
BACKEND_URL="${BACKEND_URL:-}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BACKEND_ONLY="${BACKEND_ONLY:-false}"
FRONTEND_ONLY="${FRONTEND_ONLY:-false}"

if [ -z "$PROJECT_ID" ]; then
  echo "Set PROJECT_ID (e.g. export PROJECT_ID=my-gcp-project)" >&2
  exit 1
fi

# Optional: use backend_url from Terraform output when BACKEND_URL not set
if [ -z "$BACKEND_URL" ] && [ -d "terraform/gcp" ]; then
  TF_OUT="$(cd terraform/gcp 2>/dev/null && terraform output -raw backend_url 2>/dev/null)" || true
  if [ -n "$TF_OUT" ] && [ "$TF_OUT" != "null" ]; then
    BACKEND_URL="$TF_OUT"
    echo "Using BACKEND_URL from terraform output: $BACKEND_URL"
  fi
fi

REGISTRY="${REGION}-docker.pkg.dev"
IMAGE_BASE="${REGISTRY}/${PROJECT_ID}/${REPO_ID}"

echo "Configuring Docker for Artifact Registry..."
gcloud auth configure-docker "${REGISTRY}" --quiet

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BACKEND_IMAGE="${IMAGE_BASE}/backend:${IMAGE_TAG}"
FRONTEND_IMAGE="${IMAGE_BASE}/frontend:${IMAGE_TAG}"

if [ "$FRONTEND_ONLY" != "true" ]; then
  echo "Building backend: $BACKEND_IMAGE"
  docker build -f dashboard/backend/Dockerfile -t "$BACKEND_IMAGE" .
  echo "Pushing backend..."
  docker push "$BACKEND_IMAGE"
fi

if [ "$BACKEND_ONLY" != "true" ]; then
  if [ -z "$BACKEND_URL" ]; then
    echo "Warning: BACKEND_URL not set. Frontend built with placeholder; rebuild after backend is deployed."
    BACKEND_URL="https://BACKEND-URL.run.app"
  fi
  WS_URL="${BACKEND_URL/https/wss}"
  WS_URL="${WS_URL%/}/ws"
  echo "Building frontend with REACT_APP_API_URL=$BACKEND_URL REACT_APP_WS_URL=$WS_URL"
  docker build -f dashboard/frontend/Dockerfile \
    --build-arg "REACT_APP_API_URL=$BACKEND_URL" \
    --build-arg "REACT_APP_WS_URL=$WS_URL" \
    -t "$FRONTEND_IMAGE" .
  echo "Pushing frontend..."
  docker push "$FRONTEND_IMAGE"
fi

echo ""
echo "Done. Add to terraform.tfvars and run 'terraform apply':"
[ "$FRONTEND_ONLY" != "true" ] && echo "  backend_image  = \"$BACKEND_IMAGE\""
[ "$BACKEND_ONLY" != "true" ] && echo "  frontend_image = \"$FRONTEND_IMAGE\""
