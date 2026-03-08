#!/bin/bash
# Runner VM startup: install Docker, Python, clone pr-agent, write env, optional ADO agent registration.
# Idempotent; logs to stdout for GCP Serial port / startup logs.

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
# Terraform replaces $${dashboard_url} etc. BEFORE the script reaches the shell.
mkdir -p /opt/pr-agent-runner
cat > /opt/pr-agent-runner/env << 'ENVEOF'
export DASHBOARD_URL="${dashboard_url}"
export DASHBOARD_API_KEY="${dashboard_api_key}"
export PR_AGENT_CONFIG_GCS_BUCKET="${config_bucket}"
export PR_AGENT_CONFIG_GCS_PREFIX="${config_prefix}"
export GCP_RUNNER_PR_AGENT_IMAGE="${pr_agent_image}"
ENVEOF
chmod 600 /opt/pr-agent-runner/env
log "Env file written to /opt/pr-agent-runner/env."

# --- Clone PR-Agent for Python-from-clone execution (e.g. Azure Pipelines) ---
PR_AGENT_DIR=/opt/pr-agent
if [ ! -d "$$PR_AGENT_DIR/.git" ]; then
  log "Cloning PR-Agent into $$PR_AGENT_DIR..."
  git clone --depth 1 "${pr_agent_repo_url}" "$$PR_AGENT_DIR"
  pip3 install -r "$$PR_AGENT_DIR/requirements.txt" --break-system-packages 2>/dev/null || pip3 install -r "$$PR_AGENT_DIR/requirements.txt"
  log "PR-Agent clone and pip install done."
else
  log "PR-Agent already present at $$PR_AGENT_DIR."
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

# --- Optional: Azure DevOps agent auto-registration ---
%{if ado_org_url != "" && ado_pat != "" && ado_pool != ""}
AGENT_DIR=/opt/azagent
if [ ! -f "$$AGENT_DIR/.agent" ]; then
  log "Installing Azure DevOps agent..."
  useradd -m -s /bin/bash azagent 2>/dev/null || true
  usermod -aG docker azagent

  mkdir -p "$$AGENT_DIR"
  cd "$$AGENT_DIR"

  _ADO_PAT_B64=$$(echo -n ":${ado_pat}" | base64 -w0)
  AGENT_URL=$$(curl -s -H "Authorization: Basic $$_ADO_PAT_B64" \
    "${ado_org_url}/_apis/distributedtask/packages/agent?platform=linux-x64&\$$top=1&api-version=7.0" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['value'][0]['downloadUrl'])" 2>/dev/null) || true

  if [ -z "$$AGENT_URL" ]; then
    log "Could not resolve latest agent version from API; using known stable fallback."
    AGENT_URL="https://vstsagentpackage.azureedge.net/agent/4.248.0/vsts-agent-linux-x64-4.248.0.tar.gz"
  fi

  log "Downloading agent from: $$AGENT_URL"
  curl -fkSL -o agent.tar.gz "$$AGENT_URL"
  tar xzf agent.tar.gz
  rm -f agent.tar.gz

  ./bin/installdependencies.sh 2>/dev/null || apt-get install -y -qq libicu-dev 2>/dev/null || true

  chown -R azagent:azagent "$$AGENT_DIR"

  AGENT_NAME="${ado_agent_name}"
  [ -z "$$AGENT_NAME" ] && AGENT_NAME=$$(hostname)
  log "Configuring agent '$$AGENT_NAME' for pool '${ado_pool}' at ${ado_org_url}..."
  sudo -u azagent ./config.sh --unattended \
    --url "${ado_org_url}" \
    --auth pat \
    --token "${ado_pat}" \
    --pool "${ado_pool}" \
    --agent "$$AGENT_NAME" \
    --acceptTeeEula \
    --replace

  ./svc.sh install azagent
  ./svc.sh start

  log "Azure DevOps agent '$$AGENT_NAME' registered in pool '${ado_pool}' and started."
else
  log "Azure DevOps agent already configured at $$AGENT_DIR."
fi
%{endif}

# --- Verify ---
docker --version && log "Startup complete."
exit 0
