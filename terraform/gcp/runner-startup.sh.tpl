#!/bin/bash
# Runner VM startup: Docker, env file, optional image pre-pull + smoke test,
# optional ADO agent registration.  On failure the VM self-deletes to save cost.
# Idempotent; logs to stdout for GCP Serial port / startup logs.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

log() { echo "[pr-agent-runner-startup] $*"; }

# --- Self-destruct: delete this VM via GCE API to avoid idle cost ---
self_destruct() {
  log "Initiating self-destruct to avoid idle cost..."
  sleep 3
  _ZONE=$$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/zone" | rev | cut -d/ -f1 | rev) || true
  _NAME=$$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/name") || true
  _PROJECT=$$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/project/project-id") || true
  if [ -n "$${_ZONE:-}" ] && [ -n "$${_NAME:-}" ] && [ -n "$${_PROJECT:-}" ]; then
    _TOKEN=$$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null) || true
    if [ -n "$${_TOKEN:-}" ]; then
      log "Deleting VM $$_NAME in zone $$_ZONE (project $$_PROJECT)..."
      curl -sf -X DELETE -H "Authorization: Bearer $$_TOKEN" \
        "https://compute.googleapis.com/compute/v1/projects/$$_PROJECT/zones/$$_ZONE/instances/$$_NAME" >/dev/null 2>&1 || true
      log "Self-destruct request sent."
    else
      log "Could not obtain access token for self-destruct. Manual cleanup required."
    fi
  else
    log "Could not resolve instance metadata for self-destruct. Manual cleanup required."
  fi
}

cleanup_on_failure() {
  local exit_code=$$?
  log "FATAL: startup script failed (exit $$exit_code). Check console output above for details."
  self_destruct
  exit $$exit_code
}
trap cleanup_on_failure ERR

# --- Global timeout: self-destruct if startup takes longer than 15 minutes ---
(
  sleep 900
  log "TIMEOUT: startup exceeded 15 minutes. Triggering self-destruct..."
  self_destruct
  kill $$$$ 2>/dev/null || true
) &
_TIMEOUT_PID=$$!

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

# --- Env file for PR-Agent / pipeline ---
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

# --- Clone PR-Agent (only when no Docker image configured) ---
%{if pr_agent_image == ""}
PR_AGENT_DIR=/opt/pr-agent
if [ ! -d "$$PR_AGENT_DIR/.git" ]; then
  log "Cloning PR-Agent into $$PR_AGENT_DIR..."
  git clone --depth 1 "${pr_agent_repo_url}" "$$PR_AGENT_DIR"
  pip3 install -r "$$PR_AGENT_DIR/requirements.txt" --break-system-packages 2>/dev/null || pip3 install -r "$$PR_AGENT_DIR/requirements.txt"
  log "PR-Agent clone and pip install done."
else
  log "PR-Agent already present at $$PR_AGENT_DIR."
fi
%{else}
log "Docker image configured; skipping PR-Agent source clone."

# --- Pull and smoke-test the Docker image ---
if echo "${pr_agent_image}" | grep -q "docker.pkg.dev"; then
  log "Authenticating Docker with Artifact Registry..."
  _AR_REGISTRY=$$(echo "${pr_agent_image}" | cut -d/ -f1)
  _AR_TOKEN=$$(curl -sf -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  echo "$$_AR_TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$$_AR_REGISTRY" \
    && log "Docker authenticated with $$_AR_REGISTRY." \
    || { log "FATAL: Docker auth with Artifact Registry failed."; exit 1; }
fi
log "Pulling Docker image: ${pr_agent_image}"
docker pull "${pr_agent_image}"
log "Docker image pulled successfully."
log "Smoke-testing Docker image..."
docker run --rm --entrypoint python3 "${pr_agent_image}" -c "import pr_agent; print('pr-agent container OK')" \
  && log "Docker smoke test passed." \
  || { log "WARN: Docker smoke test command failed (image may still work for pipeline)."; }
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
  log "Agent package downloaded. Extracting..."
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

# --- Done ---
kill $$_TIMEOUT_PID 2>/dev/null || true
docker --version && log "Startup complete."
exit 0
