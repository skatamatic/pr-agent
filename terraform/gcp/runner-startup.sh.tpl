#!/bin/bash
# Runner VM startup: install Docker, Python, clone pr-agent, write env for DASHBOARD_URL and GCS config.
# Idempotent; logs to stdout for GCP Serial port / startup logs.
# After this, install Azure DevOps or GitHub Actions agent; run PR-Agent via Docker or Python from /opt/pr-agent.

set -e
export DEBIAN_FRONTEND=noninteractive

log() { echo "[pr-agent-runner-startup] $*"; }

# --- System packages: Docker CE, Python, git ---
log "Installing Docker CE and system packages..."
if ! command -v docker &>/dev/null; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $$(. /etc/os-release && echo \"$${VERSION_CODENAME:-$$UBUNTU_CODENAME}\") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io
  log "Docker installed."
else
  log "Docker already installed."
fi

if ! command -v git &>/dev/null || ! command -v python3 &>/dev/null; then
  apt-get update -qq && apt-get install -y -qq python3-pip git python3-venv
  log "Python and git installed."
else
  log "Python and git already present."
fi

# --- Env file for PR-Agent / pipeline (source in pipeline or pass into Docker) ---
# 'ENVEOF' is single-quoted so shell won't expand $ signs in Terraform-interpolated values.
# Terraform replaces ${dashboard_url} etc. BEFORE the script reaches the shell.
mkdir -p /opt/pr-agent-runner
cat > /opt/pr-agent-runner/env << 'ENVEOF'
export DASHBOARD_URL="${dashboard_url}"
export PR_AGENT_CONFIG_GCS_BUCKET="${config_bucket}"
export PR_AGENT_CONFIG_GCS_PREFIX="${config_prefix}"
ENVEOF
chmod 644 /opt/pr-agent-runner/env
log "Env file written to /opt/pr-agent-runner/env."

# --- Clone PR-Agent for Python-from-clone execution (e.g. Azure Pipelines) ---
PR_AGENT_DIR=/opt/pr-agent
if [ ! -d "$PR_AGENT_DIR/.git" ]; then
  log "Cloning PR-Agent into $PR_AGENT_DIR..."
  git clone --depth 1 "${pr_agent_repo_url}" "$PR_AGENT_DIR"
  pip3 install -r "$PR_AGENT_DIR/requirements.txt" --break-system-packages 2>/dev/null || pip3 install -r "$PR_AGENT_DIR/requirements.txt"
  log "PR-Agent clone and pip install done."
else
  log "PR-Agent already present at $PR_AGENT_DIR."
fi

# --- Optional: pre-pull PR-Agent Docker image (speeds up first GitHub Actions job) ---
%{if pr_agent_image != ""}
# Authenticate Docker with Artifact Registry if needed (GCE metadata token)
if echo "${pr_agent_image}" | grep -q "docker.pkg.dev"; then
  log "Authenticating Docker with Artifact Registry..."
  _AR_REGISTRY=$$(echo "${pr_agent_image}" | cut -d/ -f1)
  _AR_TOKEN=$$(curl -s -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  echo "$$_AR_TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$$_AR_REGISTRY" 2>/dev/null \
    && log "Docker authenticated with $$_AR_REGISTRY." \
    || log "Docker auth failed (non-fatal); pull may still fail."
fi
if ! docker image inspect "${pr_agent_image}" &>/dev/null; then
  log "Pre-pulling Docker image: ${pr_agent_image}"
  docker pull "${pr_agent_image}" || log "Pre-pull failed (non-fatal); first job will pull."
else
  log "Docker image ${pr_agent_image} already present."
fi
%{endif}

# --- Verify ---
docker --version && log "Startup complete. Install ADO/GitHub agent; use Docker (e.g. uses: docker://codiumai/pr-agent:...) or Python from $PR_AGENT_DIR with env from /opt/pr-agent-runner/env."
exit 0
