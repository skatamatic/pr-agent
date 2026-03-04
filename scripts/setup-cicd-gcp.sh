#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup-cicd-gcp.sh  --  One-run script to provision GCP infrastructure and
# set up a Cloud Build CI/CD pipeline for the PR-Agent Dashboard.
#
# What it does:
#   1. Provisions all GCP infra via Terraform (Cloud SQL, VPC, Artifact
#      Registry, Secret Manager, Cloud Run, Scheduler).
#   2. Builds and deploys the dashboard backend + frontend for the first time.
#   3. Creates a Cloud Build trigger connected to your GitHub repo so that
#      subsequent pushes to the appropriate branch automatically build and
#      deploy.
#
# Prerequisites: gcloud, terraform, docker, gh (GitHub CLI)
#
# Usage:
#   ./scripts/setup-cicd-gcp.sh --env dev --project my-gcp-project
#   ./scripts/setup-cicd-gcp.sh --env prod --project my-gcp-project --region us-east1
#   ./scripts/setup-cicd-gcp.sh --env stage --project my-gcp-project --auto-approve
#   ./scripts/setup-cicd-gcp.sh --env all --project my-gcp-project --auto-approve
# ---------------------------------------------------------------------------

set -euo pipefail

# ========================== Argument parsing ===============================

ENV=""
PROJECT_ID=""
REGION="us-central1"
AUTO_APPROVE=""
SKIP_INITIAL_DEPLOY=""

usage() {
  cat <<EOF
Usage: $0 --env <dev|stage|prod|all> --project <gcp-project-id> [options]

Required:
  --env       Deployment environment: dev, stage, prod, or all
              'all' deploys dev, stage, and prod (creates missing branches)
  --project   GCP project ID

Options:
  --region           GCP region (default: us-central1)
  --auto-approve     Skip Terraform confirmation prompts
  --skip-deploy      Skip the initial Docker build/deploy (infra + trigger only)
  -h, --help         Show this help
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)        ENV="$2"; shift 2 ;;
    --project)    PROJECT_ID="$2"; shift 2 ;;
    --region)     REGION="$2"; shift 2 ;;
    --auto-approve) AUTO_APPROVE="-auto-approve"; shift ;;
    --skip-deploy)  SKIP_INITIAL_DEPLOY=1; shift ;;
    -h|--help)    usage ;;
    *)            echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$ENV" ]]        && { echo "Error: --env is required (dev, stage, prod, or all)"; usage; }
[[ -z "$PROJECT_ID" ]] && { echo "Error: --project is required"; usage; }

# ========================== "all" mode handler =============================

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

if [[ "$ENV" == "all" ]]; then
  echo "============================================================"
  echo "  PR-Agent Dashboard CI/CD Setup -- ALL ENVIRONMENTS"
  echo "============================================================"
  echo "  Project : $PROJECT_ID"
  echo "  Region  : $REGION"
  echo "============================================================"
  echo ""

  # --- Detect GitHub repo ---
  GITHUB_REPO=""
  if gh repo view --json nameWithOwner -q '.nameWithOwner' &>/dev/null; then
    GITHUB_REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
  fi
  if [[ -z "$GITHUB_REPO" ]]; then
    REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
    if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+/[^/.]+) ]]; then
      GITHUB_REPO="${BASH_REMATCH[1]}"
    fi
  fi
  if [[ -z "$GITHUB_REPO" ]]; then
    echo "Error: Could not detect GitHub repo."
    exit 1
  fi
  echo "  Repository: $GITHUB_REPO"
  echo ""

  # --- Ensure required branches exist ---
  echo "=== Ensuring required branches exist ==="
  MAIN_SHA=$(git ls-remote --heads origin main | awk '{print $1}')
  if [[ -z "$MAIN_SHA" ]]; then
    echo "Error: 'main' branch not found on remote. Push your main branch first."
    exit 1
  fi
  echo "  main   : ${MAIN_SHA:0:8}"

  for REQ_BRANCH in develop staging; do
    BRANCH_SHA=$(git ls-remote --heads origin "$REQ_BRANCH" | awk '{print $1}')
    if [[ -n "$BRANCH_SHA" ]]; then
      echo "  $REQ_BRANCH : ${BRANCH_SHA:0:8} (exists)"
    else
      echo "  $REQ_BRANCH : missing -- creating from main ..."
      gh api "repos/${GITHUB_REPO}/git/refs" \
        -f "ref=refs/heads/${REQ_BRANCH}" \
        -f "sha=${MAIN_SHA}" --silent
      git fetch origin "$REQ_BRANCH" 2>/dev/null || true
      echo "    Created '$REQ_BRANCH'"
    fi
  done
  echo ""

  # --- Recurse for each environment ---
  EXTRA_ARGS=()
  [[ -n "$AUTO_APPROVE" ]] && EXTRA_ARGS+=("--auto-approve")
  [[ -n "$SKIP_INITIAL_DEPLOY" ]] && EXTRA_ARGS+=("--skip-deploy")

  for DEPLOY_ENV in dev stage prod; do
    echo ""
    echo "########################################################################"
    echo "##  Deploying environment: $DEPLOY_ENV"
    echo "########################################################################"
    echo ""
    if ! bash "$SCRIPT_PATH" --env "$DEPLOY_ENV" --project "$PROJECT_ID" --region "$REGION" "${EXTRA_ARGS[@]}"; then
      echo "Error: Deployment of '$DEPLOY_ENV' failed."
      exit 1
    fi
  done

  echo ""
  echo "============================================================"
  echo "  All environments deployed successfully!"
  echo "============================================================"
  echo "  Environments: dev, stage, prod"
  echo "  Project:      $PROJECT_ID"
  echo "  Region:       $REGION"
  echo ""
  echo "  Push to 'develop' -> deploys dev"
  echo "  Push to 'staging' -> deploys stage"
  echo "  Push to 'main'    -> deploys prod"
  echo ""
  echo "  Monitor builds:"
  echo "    https://console.cloud.google.com/cloud-build/builds?project=$PROJECT_ID"
  echo "============================================================"
  exit 0
fi

# ========================== Environment mapping ============================

case "$ENV" in
  dev)
    BRANCH="develop"
    PREFIX="pr-agent-dash-dev"
    ;;
  stage)
    BRANCH="staging"
    PREFIX="pr-agent-dash-stage"
    ;;
  prod)
    BRANCH="main"
    PREFIX="pr-agent-dash"
    ;;
  *)
    echo "Error: --env must be dev, stage, prod, or all (got: $ENV)"
    exit 1
    ;;
esac

REPO_ID="${PREFIX}-repo"
STATE_PREFIX="pr-agent-dash/${ENV}/state"
TFSTATE_BUCKET="${PROJECT_ID}-tfstate"
REGISTRY="${REGION}-docker.pkg.dev"
IMAGE_BASE="${REGISTRY}/${PROJECT_ID}/${REPO_ID}"
BACKEND_IMAGE="${IMAGE_BASE}/backend:latest"
FRONTEND_IMAGE="${IMAGE_BASE}/frontend:latest"
CONN_NAME="${PREFIX}-github"
TRIGGER_NAME="${PREFIX}-deploy"

TF_DIR="${REPO_ROOT}/terraform/gcp"

echo "============================================================"
echo "  PR-Agent Dashboard CI/CD Setup"
echo "============================================================"
echo "  Environment : $ENV"
echo "  Branch      : $BRANCH"
echo "  Project     : $PROJECT_ID"
echo "  Region      : $REGION"
echo "  Prefix      : $PREFIX"
echo "  Repo ID     : $REPO_ID"
echo "  TF state    : gs://${TFSTATE_BUCKET}/${STATE_PREFIX}"
echo "============================================================"
echo ""

# ========================== Prerequisites ==================================

echo "=== Checking prerequisites ==="

for cmd in gcloud terraform docker gh; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: '$cmd' is required but not found in PATH."
    exit 1
  fi
done
echo "  All tools found: gcloud, terraform, docker, gh"

# Verify gcloud is authenticated and set the project
gcloud config set project "$PROJECT_ID" --quiet
ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)
if [[ -z "$ACCOUNT" ]]; then
  echo "Error: gcloud is not authenticated. Run 'gcloud auth login' first."
  exit 1
fi
echo "  gcloud authenticated as: $ACCOUNT"

# ========================== Detect GitHub repo =============================

echo ""
echo "=== Detecting GitHub repository ==="

GITHUB_REPO=""
if gh repo view --json nameWithOwner -q '.nameWithOwner' &>/dev/null; then
  GITHUB_REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
fi

if [[ -z "$GITHUB_REPO" ]]; then
  REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
  if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+/[^/.]+) ]]; then
    GITHUB_REPO="${BASH_REMATCH[1]}"
  fi
fi

if [[ -z "$GITHUB_REPO" ]]; then
  echo "Error: Could not detect GitHub repo. Ensure 'gh' is authenticated or"
  echo "       'git remote origin' points to a GitHub repo."
  exit 1
fi

GITHUB_OWNER="${GITHUB_REPO%%/*}"
GITHUB_REPO_NAME="${GITHUB_REPO##*/}"
GITHUB_REMOTE_URI="https://github.com/${GITHUB_REPO}.git"

echo "  Repository: $GITHUB_REPO"
echo "  Owner:      $GITHUB_OWNER"
echo "  Remote URI: $GITHUB_REMOTE_URI"

# ========================== Enable GCP APIs ================================

echo ""
echo "=== Enabling GCP APIs ==="

APIS=(
  cloudbuild.googleapis.com
  run.googleapis.com
  sqladmin.googleapis.com
  secretmanager.googleapis.com
  artifactregistry.googleapis.com
  compute.googleapis.com
  servicenetworking.googleapis.com
  vpcaccess.googleapis.com
  storage.googleapis.com
  cloudscheduler.googleapis.com
  iam.googleapis.com
)

for api in "${APIS[@]}"; do
  echo "  Enabling $api ..."
  gcloud services enable "$api" --quiet
done
echo "  All APIs enabled."

# ========================== Terraform state bucket =========================

echo ""
echo "=== Setting up Terraform state bucket ==="

if gcloud storage buckets describe "gs://${TFSTATE_BUCKET}" &>/dev/null; then
  echo "  Bucket gs://${TFSTATE_BUCKET} already exists."
else
  echo "  Creating gs://${TFSTATE_BUCKET} ..."
  gcloud storage buckets create "gs://${TFSTATE_BUCKET}" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
  gcloud storage buckets update "gs://${TFSTATE_BUCKET}" --versioning
  echo "  Bucket created with versioning enabled."
fi

# ========================== Generate Terraform files =======================

echo ""
echo "=== Generating Terraform configuration ==="

cat > "${TF_DIR}/backend.tf" <<EOF
terraform {
  backend "gcs" {
    bucket = "${TFSTATE_BUCKET}"
    prefix = "${STATE_PREFIX}"
  }
}
EOF
echo "  Generated backend.tf (state: gs://${TFSTATE_BUCKET}/${STATE_PREFIX})"

cat > "${TF_DIR}/terraform.tfvars" <<EOF
# Generated by setup-cicd-gcp.sh (env=${ENV}) -- do not commit secrets.
project_id = "${PROJECT_ID}"
region     = "${REGION}"
prefix     = "${PREFIX}"
EOF
echo "  Generated terraform.tfvars (prefix=${PREFIX})"

# ========================== Terraform init + apply (infra) =================

echo ""
echo "=== Terraform init ==="
cd "$TF_DIR"
terraform init -input=false -reconfigure

echo ""
# On re-run: pass existing Cloud Run images so Terraform does not destroy live services
EXISTING_BACKEND_IMAGE=""
EXISTING_FRONTEND_IMAGE=""
EXISTING_BACKEND_IMAGE=$(gcloud run services describe "${PREFIX}-backend" --region="$REGION" --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)
EXISTING_FRONTEND_IMAGE=$(gcloud run services describe "${PREFIX}-frontend" --region="$REGION" --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)
TF_APPLY_EXTRA=""
if [[ -n "$EXISTING_BACKEND_IMAGE" ]]; then TF_APPLY_EXTRA="${TF_APPLY_EXTRA} -var=backend_image=${EXISTING_BACKEND_IMAGE}"; fi
if [[ -n "$EXISTING_FRONTEND_IMAGE" ]]; then TF_APPLY_EXTRA="${TF_APPLY_EXTRA} -var=frontend_image=${EXISTING_FRONTEND_IMAGE}"; fi
if [[ -n "$EXISTING_BACKEND_IMAGE" || -n "$EXISTING_FRONTEND_IMAGE" ]]; then
  echo "  Terraform apply (using existing Cloud Run images to avoid destroying live services)"
else
  echo "  Terraform apply (infrastructure; no images yet)"
fi
terraform apply -input=false $TF_APPLY_EXTRA $AUTO_APPROVE

# ========================== Initial build + deploy =========================

if [[ -n "$SKIP_INITIAL_DEPLOY" ]]; then
  echo ""
  echo "=== Skipping initial Docker build/deploy (--skip-deploy) ==="
  echo "  (Use --skip-deploy only when resuming after GitHub OAuth or when services already exist.)"
else
  echo ""
  echo "=== Configuring Docker for Artifact Registry ==="
  gcloud auth configure-docker "${REGISTRY}" --quiet

  echo ""
  echo "=== Building and pushing backend ==="
  cd "$REPO_ROOT"
  docker build -f dashboard/backend/Dockerfile -t "$BACKEND_IMAGE" .
  docker push "$BACKEND_IMAGE"

  echo ""
  echo "=== Deploying backend via Terraform ==="
  cd "$TF_DIR"
  terraform apply -input=false -var="backend_image=${BACKEND_IMAGE}" $AUTO_APPROVE

  BACKEND_URL=$(terraform output -raw backend_url 2>/dev/null || true)
  if [[ -z "$BACKEND_URL" || "$BACKEND_URL" == "null" ]]; then
    echo "Error: backend_url output missing after deploy."
    exit 1
  fi
  WS_URL="${BACKEND_URL/https/wss}"
  WS_URL="${WS_URL%/}/ws"

  echo ""
  echo "=== Building and pushing frontend (API_URL=$BACKEND_URL) ==="
  cd "$REPO_ROOT"
  docker build -f dashboard/frontend/Dockerfile \
    --build-arg "REACT_APP_API_URL=$BACKEND_URL" \
    --build-arg "REACT_APP_WS_URL=$WS_URL" \
    -t "$FRONTEND_IMAGE" .
  docker push "$FRONTEND_IMAGE"

  echo ""
  echo "=== Deploying frontend + setting CORS URLs ==="
  cd "$TF_DIR"
  terraform apply -input=false \
    -var="backend_image=${BACKEND_IMAGE}" \
    -var="frontend_image=${FRONTEND_IMAGE}" \
    -var="backend_base_url=${BACKEND_URL}" \
    -var="frontend_base_url=" \
    $AUTO_APPROVE

  FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || true)
  if [[ -n "$FRONTEND_URL" && "$FRONTEND_URL" != "null" ]]; then
    echo "=== Second Terraform apply (frontend_base_url for CORS) ==="
    terraform apply -input=false \
      -var="backend_image=${BACKEND_IMAGE}" \
      -var="frontend_image=${FRONTEND_IMAGE}" \
      -var="backend_base_url=${BACKEND_URL}" \
      -var="frontend_base_url=${FRONTEND_URL}" \
      $AUTO_APPROVE
  fi

  echo ""
  echo "=== Waiting for backend health (up to 120s) ==="
  HEALTHY=""
  for i in $(seq 1 24); do
    if curl -sf "${BACKEND_URL}/api/health" >/dev/null 2>&1; then
      echo "  Backend healthy."
      HEALTHY=1
      break
    fi
    echo "  Attempt $i/24 ..."
    sleep 5
  done
  if [[ -z "$HEALTHY" ]]; then
    echo "  Warning: health check did not succeed; deployment may still be rolling out."
  fi
fi

# ========================== Cloud Build SA permissions ======================

echo ""
echo "=== Granting Cloud Build service account permissions ==="

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

declare -a CB_ROLES=(
  "roles/run.admin"
  "roles/iam.serviceAccountUser"
  "roles/artifactregistry.writer"
  "roles/secretmanager.secretAccessor"
  "roles/storage.objectViewer"
)

for role in "${CB_ROLES[@]}"; do
  echo "  Granting $role to Cloud Build SA ..."
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CB_SA}" \
    --role="$role" \
    --condition=None \
    --quiet >/dev/null 2>&1 || true
done

CB_P4SA="service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
echo "  Granting roles/secretmanager.admin to Cloud Build P4SA (for GitHub connection) ..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CB_P4SA}" \
  --role="roles/secretmanager.admin" \
  --condition=None \
  --quiet >/dev/null 2>&1 || true
echo "  Cloud Build SA permissions configured."

# ========================== Cloud Build GitHub connection ===================

echo ""
echo "=== Setting up Cloud Build GitHub connection ==="
echo "  (This may open a browser for one-time GitHub OAuth authorization.)"
echo ""

# Check if connection already exists
EXISTING_CONN=$(gcloud builds connections describe "$CONN_NAME" \
  --region="$REGION" --format='value(name)' 2>/dev/null || true)

if [[ -n "$EXISTING_CONN" ]]; then
  echo "  Connection '$CONN_NAME' already exists."
else
  echo "  Creating connection '$CONN_NAME' ..."
  gcloud builds connections create github "$CONN_NAME" \
    --region="$REGION"
  echo "  Connection created. If prompted, authorize Cloud Build in your browser."
fi

# Wait for installation state to be COMPLETE; open browser when auth URL is available
echo "  Verifying connection installation state ..."
CONN_READY=""
BROWSER_OPENED=""
for i in $(seq 1 24); do
  STATE=$(gcloud builds connections describe "$CONN_NAME" \
    --region="$REGION" --format='value(installationState.stage)' 2>/dev/null || true)
  if [[ "$STATE" == "COMPLETE" ]]; then
    echo "  Connection installation: COMPLETE"
    CONN_READY=1
    break
  fi
  if [[ "$STATE" == "PENDING_INSTALL_APP" || "$STATE" == "PENDING_USER_OAUTH" ]]; then
    if [[ -z "$BROWSER_OPENED" ]]; then
      AUTH_URL=$(gcloud builds connections describe "$CONN_NAME" \
        --region="$REGION" --format='value(installationState.actionUri)' 2>/dev/null || true)
      if [[ -n "$AUTH_URL" ]]; then
        echo "  >>> Authorize Cloud Build (one-time). Opening in your default browser:"
        echo "  >>> $AUTH_URL"
        echo ""
        BROWSER_OPENED=1
        if command -v xdg-open &>/dev/null; then
          xdg-open "$AUTH_URL" 2>/dev/null && echo "  Browser launched. Complete the authorization, then this script will continue." || echo "  (Could not launch browser — please open the URL above manually.)"
        elif command -v open &>/dev/null; then
          open "$AUTH_URL" 2>/dev/null && echo "  Browser launched. Complete the authorization, then this script will continue." || echo "  (Could not launch browser — please open the URL above manually.)"
        else
          echo "  (Could not launch browser — please open the URL above manually.)"
        fi
      fi
    fi
  fi
  echo "  Installation state: ${STATE:-pending} (attempt $i/24, waiting 10s) ..."
  sleep 10
done

if [[ -z "$CONN_READY" ]]; then
  echo ""
  echo "  To finish: open the URL shown above in your browser, complete the GitHub authorization,"
  echo "  then re-run this script. (It will skip completed steps and create the trigger.)"
  echo ""
  echo "Error: GitHub connection did not reach COMPLETE state within 4 minutes. Authorize in browser, then re-run."
  exit 1
fi

# ========================== Link GitHub repository =========================

echo ""
echo "=== Linking GitHub repository ==="

CB_REPO_NAME="${GITHUB_REPO_NAME}-${ENV}"
EXISTING_REPO=$(gcloud builds repositories describe "$CB_REPO_NAME" \
  --connection="$CONN_NAME" --region="$REGION" --format='value(name)' 2>/dev/null || true)

if [[ -n "$EXISTING_REPO" ]]; then
  echo "  Repository link '$CB_REPO_NAME' already exists."
else
  echo "  Linking $GITHUB_REMOTE_URI as '$CB_REPO_NAME' ..."
  gcloud builds repositories create "$CB_REPO_NAME" \
    --connection="$CONN_NAME" \
    --region="$REGION" \
    --remote-uri="$GITHUB_REMOTE_URI"
  echo "  Repository linked."
fi

REPO_RESOURCE="projects/${PROJECT_ID}/locations/${REGION}/connections/${CONN_NAME}/repositories/${CB_REPO_NAME}"

# ========================== Create Cloud Build trigger =====================

echo ""
echo "=== Creating Cloud Build trigger ==="

EXISTING_TRIGGER=$(gcloud builds triggers describe "$TRIGGER_NAME" \
  --region="$REGION" --format='value(name)' 2>/dev/null || true)

if [[ -n "$EXISTING_TRIGGER" ]]; then
  echo "  Trigger '$TRIGGER_NAME' already exists. Replacing ..."
  gcloud builds triggers delete "$TRIGGER_NAME" \
    --region="$REGION" --quiet 2>/dev/null || true
fi

CB_SA_RESOURCE="projects/${PROJECT_ID}/serviceAccounts/${CB_SA}"
if ! gcloud builds triggers create github \
  --name="$TRIGGER_NAME" \
  --region="$REGION" \
  --repository="$REPO_RESOURCE" \
  --branch-pattern="^${BRANCH}$" \
  --build-config="cloudbuild-deploy.yaml" \
  --included-files="dashboard/**,terraform/gcp/**,cloudbuild-deploy.yaml" \
  --substitutions="_REGION=${REGION},_REPO_ID=${REPO_ID},_PREFIX=${PREFIX}" \
  --service-account="$CB_SA_RESOURCE"; then
  echo "Error: Failed to create Cloud Build trigger '$TRIGGER_NAME'."
  exit 1
fi

echo "  Trigger '$TRIGGER_NAME' created."
echo "  Branch filter: ^${BRANCH}$"
echo "  Watched paths: dashboard/**, terraform/gcp/**, cloudbuild-deploy.yaml"

# ========================== Create PR-Agent image trigger ==================

echo ""
echo "=== Creating PR-Agent image trigger ==="

AGENT_TRIGGER_NAME="${PREFIX}-agent"
EXISTING_AGENT_TRIGGER=$(gcloud builds triggers describe "$AGENT_TRIGGER_NAME" \
  --region="$REGION" --format='value(name)' 2>/dev/null || true)

if [[ -n "$EXISTING_AGENT_TRIGGER" ]]; then
  echo "  Trigger '$AGENT_TRIGGER_NAME' already exists. Replacing ..."
  gcloud builds triggers delete "$AGENT_TRIGGER_NAME" \
    --region="$REGION" --quiet 2>/dev/null || true
fi

if ! gcloud builds triggers create github \
  --name="$AGENT_TRIGGER_NAME" \
  --region="$REGION" \
  --repository="$REPO_RESOURCE" \
  --branch-pattern="^${BRANCH}$" \
  --build-config="cloudbuild-pr-agent.yaml" \
  --included-files="pr_agent/**,docker/Dockerfile.github_action_runner,requirements.txt,.dockerignore.pr-agent,cloudbuild-pr-agent.yaml" \
  --substitutions="_REGION=${REGION},_REPO_ID=${REPO_ID},_PREFIX=${PREFIX}" \
  --service-account="$CB_SA_RESOURCE"; then
  echo "Error: Failed to create Cloud Build trigger '$AGENT_TRIGGER_NAME'."
  exit 1
fi

echo "  Trigger '$AGENT_TRIGGER_NAME' created."
echo "  Branch filter: ^${BRANCH}$"
echo "  Watched paths: pr_agent/**, docker/Dockerfile.github_action_runner, requirements.txt, .dockerignore.pr-agent"

# ========================== Summary ========================================

echo ""
echo "============================================================"
echo "  CI/CD Setup Complete!"
echo "============================================================"
echo ""
echo "  Environment : $ENV"
echo "  Project     : $PROJECT_ID"
echo "  Region      : $REGION"
echo ""

if [[ -z "$SKIP_INITIAL_DEPLOY" ]]; then
  BACKEND_URL=$(cd "$TF_DIR" && terraform output -raw backend_url 2>/dev/null || true)
  FRONTEND_URL=$(cd "$TF_DIR" && terraform output -raw frontend_url 2>/dev/null || true)
  API_KEY=$(cd "$TF_DIR" && terraform output -raw dashboard_api_key 2>/dev/null || true)
  CONFIG_BUCKET=$(cd "$TF_DIR" && terraform output -raw config_bucket 2>/dev/null || true)

  echo "  Backend URL : ${BACKEND_URL:-n/a}"
  echo "  Frontend URL: ${FRONTEND_URL:-n/a}"
  echo ""
  if [[ -n "$API_KEY" && "$API_KEY" != "null" ]]; then
    echo "  DASHBOARD_API_KEY: $API_KEY"
    echo "  (Set this in PR-Agent env or pipeline secrets.)"
    echo ""
  fi
  if [[ -n "$CONFIG_BUCKET" && "$CONFIG_BUCKET" != "null" ]]; then
    echo "  Config bucket: PR_AGENT_CONFIG_GCS_BUCKET=$CONFIG_BUCKET"
    echo ""
  fi
fi

echo "  Cloud Build triggers:"
echo "    $TRIGGER_NAME       (dashboard deploy)"
echo "    $AGENT_TRIGGER_NAME  (PR-Agent image)"
echo "  Watches branch: $BRANCH"
echo ""
echo "  Push to '$BRANCH' to trigger automatic builds + deploy."
echo "  Monitor builds: https://console.cloud.google.com/cloud-build/builds?project=$PROJECT_ID"
if [[ -n "$SKIP_INITIAL_DEPLOY" ]]; then
  echo ""
  echo "  Note: You used --skip-deploy. If Cloud Run backend/frontend do not exist yet,"
  echo "  the first push will build images but deploy steps will fail. Run this script"
  echo "  without --skip-deploy to deploy the initial images, then pushes will auto-deploy."
fi
echo ""
echo "  To re-run infra changes manually:"
echo "    cd terraform/gcp && terraform apply"
echo "============================================================"
