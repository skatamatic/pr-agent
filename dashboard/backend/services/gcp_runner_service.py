"""
GCP Runner VM service: provision and deprovision Compute Engine VMs for self-hosted
GitHub Actions / Azure DevOps runners. Used when a repo is connected via a runner connection
and the dashboard is configured for GCP (GCP_RUNNER_PROJECT_ID, etc.).
"""
import logging
import re
import shlex
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Optional: only required when GCP runner provisioning is used
try:
    from google.cloud import compute_v1
    from google.api_core.exceptions import NotFound as GCPNotFound
    GCP_COMPUTE_AVAILABLE = True
except ImportError:
    GCP_COMPUTE_AVAILABLE = False
    compute_v1 = None
    GCPNotFound = None


def _safe_instance_name(name: str, unique_id: str = "") -> str:
    """GCE instance names must match [a-z]([-a-z0-9]*[a-z0-9])? (RFC 1035, 1-63 chars)."""
    s = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    if not s or not s[0].isalpha():
        s = "r-" + s
    if unique_id:
        suffix = "-" + str(unique_id)
        s = s[:63 - len(suffix)].rstrip("-") + suffix
    else:
        s = s[:63].rstrip("-")
    return s or "runner"


def _shell_safe(value: str) -> str:
    """Escape a value for safe embedding in a shell script."""
    return shlex.quote(str(value)) if value else "''"


def _get_startup_script(
    dashboard_url: str,
    config_bucket: str = "",
    config_prefix: str = "pr-agent-config/",
    pr_agent_repo_url: str = "https://github.com/Codium-ai/pr-agent.git",
    pr_agent_image: str = "",
    dashboard_api_key: str = "",
    ado_org_url: str = "",
    ado_pat: str = "",
    ado_pool: str = "",
    ado_agent_name: str = "",
) -> str:
    """Build startup script equivalent to terraform/gcp/runner-startup.sh.tpl.
    Keep in sync: same sections, env vars, and optional pre-pull block.
    When ado_org_url + ado_pat + ado_pool are provided, auto-registers the Azure DevOps agent."""
    raw_ado_org_url = (ado_org_url or "").strip()
    raw_ado_pat = (ado_pat or "").strip()
    raw_ado_pool = (ado_pool or "").strip()

    dashboard_url = _shell_safe(dashboard_url)
    config_bucket = _shell_safe(config_bucket)
    config_prefix = _shell_safe(config_prefix)
    pr_agent_repo_url = _shell_safe(pr_agent_repo_url)
    pr_agent_image_safe = _shell_safe(pr_agent_image) if pr_agent_image else ""
    dashboard_api_key = _shell_safe(dashboard_api_key)
    ado_org_url = _shell_safe(raw_ado_org_url)
    ado_pat = _shell_safe(raw_ado_pat)
    ado_pool = _shell_safe(raw_ado_pool)
    ado_agent_name = _shell_safe(ado_agent_name)

    pre_pull_block = ""
    if pr_agent_image:
        ar_auth_block = ""
        if "docker.pkg.dev" in pr_agent_image:
            ar_auth_block = f"""
# Authenticate Docker with Artifact Registry (GCE metadata token)
log "Authenticating Docker with Artifact Registry..."
_AR_REGISTRY=$(echo {pr_agent_image_safe} | cut -d/ -f1)
_AR_TOKEN=$(curl -sf -H "Metadata-Flavor: Google" \\
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$_AR_TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$_AR_REGISTRY" \\
  && log "Docker authenticated with $_AR_REGISTRY." \\
  || {{ log "FATAL: Docker auth with Artifact Registry failed."; exit 1; }}
"""
        pre_pull_block = f"""{ar_auth_block}
log "Pulling Docker image: {pr_agent_image_safe}"
docker pull {pr_agent_image_safe}
log "Docker image pulled successfully."
log "Smoke-testing Docker image..."
docker run --rm --entrypoint python3 {pr_agent_image_safe} -c "import pr_agent; print('pr-agent container OK')" \\
  && log "Docker smoke test passed." \\
  || {{ log "WARN: Docker smoke test command failed (image may still work for pipeline)."; }}
"""

    ado_agent_block = ""
    if raw_ado_org_url and raw_ado_pat and raw_ado_pool:
        agent_name_expr = f'{ado_agent_name}' if ado_agent_name else '"$(hostname)"'
        ado_agent_block = f"""
# --- Azure DevOps agent auto-registration ---
AGENT_DIR=/opt/azagent
if [ ! -f "$AGENT_DIR/.agent" ]; then
  log "Installing Azure DevOps agent..."
  useradd -m -s /bin/bash azagent 2>/dev/null || true
  usermod -aG docker azagent

  mkdir -p "$AGENT_DIR"
  cd "$AGENT_DIR"

  # Resolve latest agent package URL from Azure DevOps API
  _ADO_PAT_B64=$(echo -n :{ado_pat} | base64 -w0)
  AGENT_URL=$(curl -s -H "Authorization: Basic $_ADO_PAT_B64" \\
    {ado_org_url}"/_apis/distributedtask/packages/agent?platform=linux-x64&\\$top=1&api-version=7.0" \\
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['value'][0]['downloadUrl'])" 2>/dev/null) || true

  if [ -z "$AGENT_URL" ]; then
    log "Could not resolve latest agent version from API; using known stable fallback."
    AGENT_URL="https://vstsagentpackage.azureedge.net/agent/4.248.0/vsts-agent-linux-x64-4.248.0.tar.gz"
  fi

  log "Downloading agent from: $AGENT_URL"
  curl -fkSL -o agent.tar.gz "$AGENT_URL"
  log "Agent package downloaded. Extracting..."
  tar xzf agent.tar.gz
  rm -f agent.tar.gz

  # Install agent dependencies (libicu, etc.)
  ./bin/installdependencies.sh 2>/dev/null || apt-get install -y -qq libicu-dev 2>/dev/null || true

  chown -R azagent:azagent "$AGENT_DIR"

  AGENT_NAME={agent_name_expr}
  log "Configuring agent '$AGENT_NAME' for pool {ado_pool} at {ado_org_url}..."
  sudo -u azagent ./config.sh --unattended \\
    --url {ado_org_url} \\
    --auth pat \\
    --token {ado_pat} \\
    --pool {ado_pool} \\
    --agent "$AGENT_NAME" \\
    --acceptTeeEula \\
    --replace

  log "Agent configured. Installing and starting service..."
  ./svc.sh install azagent
  ./svc.sh start

  log "Azure DevOps agent '$AGENT_NAME' registered in pool {ado_pool} and started."
else
  log "Azure DevOps agent already configured at $AGENT_DIR."
fi

# Ensure Azure agent service user can read runner env (for pipeline image/config resolution).
if id azagent >/dev/null 2>&1 && [ -f /opt/pr-agent-runner/env ]; then
  chown root:azagent /opt/pr-agent-runner/env || true
  chmod 640 /opt/pr-agent-runner/env || true
  log "Adjusted /opt/pr-agent-runner/env permissions for azagent."
fi
"""

    clone_block = ""
    if not pr_agent_image:
        clone_block = f"""
# --- Clone PR-Agent for Python-from-source execution (only when no Docker image configured) ---
PR_AGENT_DIR=/opt/pr-agent
if [ ! -d "$PR_AGENT_DIR/.git" ]; then
  log "Cloning PR-Agent into $PR_AGENT_DIR..."
  git clone --depth 1 {pr_agent_repo_url} "$PR_AGENT_DIR"
  pip3 install -r "$PR_AGENT_DIR/requirements.txt" --break-system-packages 2>/dev/null || pip3 install -r "$PR_AGENT_DIR/requirements.txt"
  log "PR-Agent clone and pip install done."
else
  log "PR-Agent already present at $PR_AGENT_DIR."
fi
"""
    else:
        clone_block = """
# --- Skipping PR-Agent clone (Docker image configured; pipeline runs inside container) ---
log "Docker image configured; skipping PR-Agent source clone."
"""

    # Env file heredoc uses quoted delimiter ('ENVEOF') which prevents shell
    # expansion, so values are safe from shell injection.  Python f-string
    # substitution still happens at generation time; the original (unescaped)
    # values are intentionally used here since the heredoc body is not
    # interpreted by the shell.
    def _strip_shell_quotes(v: str) -> str:
        if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
            return v[1:-1]
        return v

    env_dashboard_url = _strip_shell_quotes(dashboard_url)
    env_dashboard_api_key = _strip_shell_quotes(dashboard_api_key)
    env_config_bucket = _strip_shell_quotes(config_bucket)
    env_config_prefix = _strip_shell_quotes(config_prefix)
    env_ado_pat = _strip_shell_quotes(ado_pat)
    env_pr_agent_image = pr_agent_image  # original value, not escaped

    return f"""#!/bin/bash
# Runner VM startup: Docker, env file, optional image pre-pull, optional ADO agent registration.
# Idempotent; logs to stdout.  On failure the VM self-deletes to avoid wasted cost.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

log() {{ echo "[pr-agent-runner-startup] $*"; }}

# --- Self-destruct: delete this VM via GCE API to avoid idle cost ---
self_destruct() {{
  log "Initiating self-destruct to avoid idle cost..."
  sleep 3
  _ZONE=$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/zone" | rev | cut -d/ -f1 | rev) || true
  _NAME=$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/name") || true
  _PROJECT=$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/project/project-id") || true
  if [ -n "${{_ZONE:-}}" ] && [ -n "${{_NAME:-}}" ] && [ -n "${{_PROJECT:-}}" ]; then
    _TOKEN=$(curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
      | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null \\
      || curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
      | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4) || true
    if [ -n "${{_TOKEN:-}}" ]; then
      log "Deleting VM $_NAME in zone $_ZONE (project $_PROJECT)..."
      for _attempt in 1 2 3; do
        curl -sf -X DELETE -H "Authorization: Bearer $_TOKEN" \\
          "https://compute.googleapis.com/compute/v1/projects/$_PROJECT/zones/$_ZONE/instances/$_NAME" >/dev/null 2>&1 && break
        log "Self-destruct attempt $_attempt failed, retrying in 5s..."
        sleep 5
      done
      log "Self-destruct request sent."
    else
      log "Could not obtain access token for self-destruct."
      if command -v gcloud &>/dev/null; then
        log "Attempting self-destruct via gcloud..."
        gcloud compute instances delete "$_NAME" --zone="$_ZONE" --project="$_PROJECT" --quiet 2>/dev/null || true
      else
        log "Manual cleanup required."
      fi
    fi
  else
    log "Could not resolve instance metadata for self-destruct. Manual cleanup required."
  fi
}}

cleanup_on_failure() {{
  local exit_code=$?
  log "FATAL: startup script failed (exit $exit_code). Check console output above for details."
  self_destruct
  exit $exit_code
}}
trap cleanup_on_failure ERR

# --- Global timeout: self-destruct if startup takes longer than 15 minutes ---
(
  sleep 900
  log "TIMEOUT: startup exceeded 15 minutes. Triggering self-destruct..."
  self_destruct
  kill $$ 2>/dev/null || true
) &
_TIMEOUT_PID=$!

# --- System packages: Docker CE, Python, git ---
log "Installing Docker CE and system packages..."
if ! command -v docker &>/dev/null; then
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${{VERSION_CODENAME:-$UBUNTU_CODENAME}}") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
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
export DASHBOARD_URL="{env_dashboard_url}"
export DASHBOARD_API_KEY="{env_dashboard_api_key}"
export PR_AGENT_CONFIG_GCS_BUCKET="{env_config_bucket}"
export PR_AGENT_CONFIG_GCS_PREFIX="{env_config_prefix}"
export AZURE_DEVOPS_PAT="{env_ado_pat}"
export GCP_RUNNER_PR_AGENT_IMAGE="{env_pr_agent_image}"
ENVEOF
chmod 600 /opt/pr-agent-runner/env
log "Env file written to /opt/pr-agent-runner/env."
{clone_block}{pre_pull_block}{ado_agent_block}
# --- Verify ---
kill $_TIMEOUT_PID 2>/dev/null || true
docker --version && log "Startup complete."
exit 0
"""


class GCPRunnerService:
    """Create and delete GCP Compute Engine VMs for action runner connections."""

    def __init__(
        self,
        project_id: str,
        region: str,
        zone: Optional[str] = None,
        machine_type: str = "e2-medium",
        subnet: Optional[str] = None,
        network: Optional[str] = None,
        name_prefix: str = "pr-agent-runner",
        dashboard_url: str = "",
        dashboard_api_key: str = "",
        config_bucket: str = "",
        config_prefix: str = "pr-agent-config/",
        pr_agent_repo_url: str = "https://github.com/Codium-ai/pr-agent.git",
        pr_agent_runner_image: str = "",
        ado_pat: str = "",
    ):
        self.project_id = project_id
        self.region = region
        self.zone = zone or f"{region}-a"
        self.machine_type = machine_type
        self.subnet = (subnet or "").strip() or None
        self.network = (network or "").strip() or None
        self.name_prefix = name_prefix
        self.dashboard_url = dashboard_url
        self.dashboard_api_key = dashboard_api_key
        self.config_bucket = config_bucket
        self.config_prefix = config_prefix
        self.pr_agent_repo_url = pr_agent_repo_url
        self.pr_agent_runner_image = pr_agent_runner_image or ""
        self.ado_pat = ado_pat
        self._client: Optional[Any] = None

    @staticmethod
    def _extract_name_from_self_link(self_link: str, resource_segment: str) -> Optional[str]:
        token = f"/{resource_segment}/"
        if token not in self_link:
            return None
        return self_link.rsplit(token, 1)[-1].strip("/") or None

    def _normalize_network_self_link(self, network_value: str) -> str:
        network = (network_value or "").strip()
        if network.startswith("http") or "/networks/" in network:
            return network
        return f"projects/{self.project_id}/global/networks/{network}"

    def _normalize_subnetwork_self_link(self, subnet_value: str) -> str:
        subnet = (subnet_value or "").strip()
        if subnet.startswith("http") or "/subnetworks/" in subnet:
            return subnet
        return f"projects/{self.project_id}/regions/{self.region}/subnetworks/{subnet}"

    def _get_network_mode(self, network_self_link: str) -> Optional[str]:
        """Best-effort network mode lookup: returns AUTO, CUSTOM, or None on unknown."""
        try:
            network_name = self._extract_name_from_self_link(network_self_link, "networks")
            if not network_name:
                return None
            net_client = compute_v1.NetworksClient()
            net = net_client.get(project=self.project_id, network=network_name)
            return "AUTO" if bool(getattr(net, "auto_create_subnetworks", False)) else "CUSTOM"
        except Exception as e:
            logger.debug("Could not determine network mode for %s: %s", network_self_link, e)
            return None

    def _find_first_subnetwork_for_network(self, network_self_link: str) -> Optional[str]:
        """Return a region subnetwork for the given network, preferring 'default'."""
        try:
            sub_client = compute_v1.SubnetworksClient()
            subs = list(sub_client.list(project=self.project_id, region=self.region))
            candidates = [s.self_link for s in subs if getattr(s, "network", "") == network_self_link and getattr(s, "self_link", "")]
            if not candidates:
                return None
            default_candidate = next((s for s in candidates if s.endswith("/subnetworks/default")), None)
            return default_candidate or candidates[0]
        except Exception as e:
            logger.debug("Could not list subnetworks for network %s in region %s: %s", network_self_link, self.region, e)
            return None

    @property
    def client(self):
        if not GCP_COMPUTE_AVAILABLE:
            raise RuntimeError("google-cloud-compute is not installed. pip install google-cloud-compute")
        if self._client is None:
            self._client = compute_v1.InstancesClient()
        return self._client

    def is_configured(self) -> bool:
        return bool(self.project_id and self.zone)

    def instance_name_for_connection(self, connection_id: int, provider: str, organization: str, project: Optional[str] = None) -> str:
        """Generate a unique, GCE-valid instance name for this connection."""
        base = f"{self.name_prefix}-{connection_id}-{provider}-{organization}"
        if project:
            base += f"-{project}"
        return _safe_instance_name(base)

    def provision(
        self,
        connection_id: int,
        provider: str,
        organization: str,
        project: Optional[str] = None,
        agent_pool: str = "",
        ado_org_url: str = "",
    ) -> Dict[str, Any]:
        """
        Create a GCE VM for this runner connection. Returns dict with instance_name, zone,
        status, message, and install_instructions for the user (copy-paste runner install).
        When provider is azure_devops and ado_pat + agent_pool are provided, the VM startup
        script will automatically register the Azure DevOps agent.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "GCP runner not configured. Set GCP_RUNNER_PROJECT_ID and GCP_RUNNER_REGION (and optionally GCP_RUNNER_ZONE).",
                "instance_name": None,
                "zone": None,
            }
        name = self.instance_name_for_connection(connection_id, provider, organization, project)

        resolved_ado_org_url = ""
        resolved_ado_pat = ""
        resolved_ado_pool = ""
        if provider == "azure_devops" and self.ado_pat and agent_pool:
            resolved_ado_org_url = (ado_org_url or "").strip() or f"https://dev.azure.com/{organization}"
            resolved_ado_pat = self.ado_pat
            resolved_ado_pool = agent_pool

        try:
            existing_status = self.get_instance_status(name, self.zone)
            if existing_status == "RUNNING":
                logger.info("GCP runner VM %s already exists and is RUNNING; returning existing instance.", name)
                agent_auto = bool(resolved_ado_org_url and resolved_ado_pat and resolved_ado_pool)
                install_instructions = self._install_instructions(provider, name, auto_registered=agent_auto, agent_pool=resolved_ado_pool)
                return {
                    "success": True,
                    "instance_name": name,
                    "zone": self.zone,
                    "message": "VM already exists and is running.",
                    "agent_auto_registered": agent_auto,
                    "agent_pool": resolved_ado_pool if agent_auto else None,
                    "install_instructions": install_instructions,
                    "operation_name": None,
                }

            startup_script = _get_startup_script(
                dashboard_url=self.dashboard_url,
                config_bucket=self.config_bucket,
                config_prefix=self.config_prefix,
                pr_agent_repo_url=self.pr_agent_repo_url,
                pr_agent_image=self.pr_agent_runner_image,
                dashboard_api_key=self.dashboard_api_key,
                ado_org_url=resolved_ado_org_url,
                ado_pat=resolved_ado_pat,
                ado_pool=resolved_ado_pool,
                ado_agent_name=name,
            )
            machine_type_path = f"zones/{self.zone}/machineTypes/{self.machine_type}"
            disk_params = compute_v1.AttachedDiskInitializeParams(
                source_image=f"projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts",
                disk_size_gb=50,
            )
            disk = compute_v1.AttachedDisk(
                boot=True,
                auto_delete=True,
                initialize_params=disk_params,
            )
            network_interface = compute_v1.NetworkInterface()
            if self.subnet:
                network_interface.subnetwork = self._normalize_subnetwork_self_link(self.subnet)
            elif self.network:
                network_self_link = self._normalize_network_self_link(self.network)
                network_interface.network = network_self_link
                mode = self._get_network_mode(network_self_link)
                if mode == "CUSTOM":
                    inferred_subnet = self._find_first_subnetwork_for_network(network_self_link)
                    if inferred_subnet:
                        network_interface.subnetwork = inferred_subnet
                    else:
                        raise RuntimeError(
                            "Selected VPC network is in custom subnet mode but no subnetwork is configured. "
                            "Set GCP_RUNNER_SUBNET (or dashboard backend gcp_runner_subnet) to a valid subnetwork."
                        )
            else:
                # Avoid sending an empty network field to Compute API.
                network_interface.network = f"projects/{self.project_id}/global/networks/default"
            network_interface.access_configs = [
                compute_v1.AccessConfig(name="External NAT", type_="ONE_TO_ONE_NAT")
            ]
            metadata_items = [
                compute_v1.Items(key="startup-script", value=startup_script),
            ]
            instance = compute_v1.Instance(
                name=name,
                machine_type=machine_type_path,
                disks=[disk],
                network_interfaces=[network_interface],
                metadata=compute_v1.Metadata(items=metadata_items),
                service_accounts=[
                    compute_v1.ServiceAccount(
                        email="default",
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                ],
                tags=compute_v1.Tags(items=["pr-agent-runner"]),
            )
            request = compute_v1.InsertInstanceRequest(
                project=self.project_id,
                zone=self.zone,
                instance_resource=instance,
            )
            op = self.client.insert(request=request)
            logger.info("GCP runner VM insert started: %s in %s", name, self.zone)
            agent_auto = bool(resolved_ado_org_url and resolved_ado_pat and resolved_ado_pool)
            install_instructions = self._install_instructions(provider, name, auto_registered=agent_auto, agent_pool=resolved_ado_pool)
            msg = (
                f"VM creation started. The Azure DevOps agent will auto-register in pool '{resolved_ado_pool}'. Allow 3-5 minutes for VM boot + agent setup."
                if agent_auto
                else "VM creation started. It may take 1–2 minutes to be running. Use the instructions below to install the runner/agent on the VM."
            )
            return {
                "success": True,
                "instance_name": name,
                "zone": self.zone,
                "message": msg,
                "agent_auto_registered": agent_auto,
                "agent_pool": resolved_ado_pool if agent_auto else None,
                "install_instructions": install_instructions,
                "operation_name": op.name if hasattr(op, "name") else None,
            }
        except Exception as e:
            logger.exception("GCP provision failed for connection %s: %s", connection_id, e)
            return {
                "success": False,
                "error": str(e),
                "instance_name": None,
                "zone": None,
            }

    def _install_instructions(self, provider: str, instance_name: str, auto_registered: bool = False, agent_pool: str = "") -> Dict[str, str]:
        """Short copy-paste instructions for ADO or GitHub runner install and PR-Agent execution (Docker vs Python)."""
        ssh_hint = f"gcloud compute ssh {instance_name} --zone={self.zone} --project={self.project_id}"
        if provider == "github":
            return {
                "ssh_command": ssh_hint,
                "steps": "1. SSH to the VM. 2. Follow GitHub Settings > Actions > Runners > New self-hosted runner to register the agent.",
                "docs_url": "https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners",
            }
        if provider == "azure_devops":
            if auto_registered:
                return {
                    "ssh_command": ssh_hint,
                    "steps": (
                        f"The Azure DevOps agent is auto-registering in pool '{agent_pool}'. "
                        "Allow 3-5 min after VM creation. Check agent status in Azure DevOps: "
                        "Project Settings > Agent Pools > your pool. "
                        "To verify via SSH: sudo /opt/azagent/svc.sh status"
                    ),
                    "docs_url": "https://learn.microsoft.com/en-us/azure/devops/pipelines/agents/linux-agent",
                }
            return {
                "ssh_command": ssh_hint,
                "steps": "1. SSH to the VM. 2. In Azure DevOps: Project Settings > Agent Pools > Add agent > Linux; run the registration script.",
                "docs_url": "https://learn.microsoft.com/en-us/azure/devops/pipelines/agents/linux-agent",
            }
        return {"ssh_command": ssh_hint, "steps": "SSH to the VM and install the runner/agent per your provider docs.", "docs_url": ""}

    def deprovision(self, instance_name: str, zone: str) -> Dict[str, Any]:
        """Delete the GCE VM. instance_name and zone should match what was stored for the connection."""
        if not self.is_configured():
            return {"success": False, "error": "GCP runner not configured."}
        if not instance_name or not zone:
            return {"success": False, "error": "instance_name and zone are required."}
        try:
            request = compute_v1.DeleteInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=instance_name,
            )
            op = self.client.delete(request=request)
            logger.info("GCP runner VM delete started: %s in %s", instance_name, zone)
            return {
                "success": True,
                "message": "VM deletion started.",
                "operation_name": op.name if hasattr(op, "name") else None,
            }
        except GCPNotFound:
            return {"success": True, "message": "Instance already deleted or not found."}
        except Exception as e:
            logger.exception("GCP deprovision failed for %s: %s", instance_name, e)
            return {"success": False, "error": str(e)}

    def get_instance_status(self, instance_name: str, zone: str) -> Optional[str]:
        """Return instance status (RUNNING, STOPPED, etc.) or None if not found/error."""
        if not GCP_COMPUTE_AVAILABLE or not self.is_configured():
            return None
        try:
            request = compute_v1.GetInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=instance_name,
            )
            instance = self.client.get(request=request)
            return instance.status if hasattr(instance, "status") else None
        except Exception:
            return None

    def get_startup_progress(self, instance_name: str, zone: str) -> Dict[str, Any]:
        """Parse startup-script progress from serial console output for UX polling.

        Milestones are built dynamically based on what the log reveals (Docker
        mode vs source-clone mode, with/without ADO agent).
        """
        progress: Dict[str, Any] = {
            "log_available": False,
            "milestones": [],
            "percent": 0,
            "console_lines": [],
            "startup_complete": False,
            "docker_ready": False,
            "env_written": False,
            "pr_agent_ready": False,
            "ado_agent_registered": False,
            "last_log_excerpt": "",
        }
        if not GCP_COMPUTE_AVAILABLE or not self.is_configured():
            return progress
        try:
            request = compute_v1.GetSerialPortOutputInstanceRequest(
                project=self.project_id,
                zone=zone,
                instance=instance_name,
                port=1,
            )
            out = self.client.get_serial_port_output(request=request)
            contents = (out.contents if hasattr(out, "contents") else "") or ""
            if not contents:
                return progress

            progress["log_available"] = True
            c = contents.lower()

            tagged_lines = [ln for ln in contents.splitlines() if "[pr-agent-runner-startup]" in ln]
            progress["console_lines"] = tagged_lines[-60:]
            progress["last_log_excerpt"] = "\n".join(tagged_lines[-8:]) if tagged_lines else ""

            uses_docker = "skipping pr-agent source clone" in c
            has_ado = "installing azure devops agent" in c or "azure devops agent already configured" in c

            milestones = [
                {"key": "system_packages", "label": "Installing system packages", "done": False},
                {"key": "docker_ready", "label": "Docker installed", "done": False},
                {"key": "python_git_ready", "label": "Python & Git ready", "done": False},
                {"key": "env_written", "label": "Environment file written", "done": False},
            ]
            if uses_docker:
                milestones.append({"key": "clone_skipped", "label": "Source clone skipped (Docker mode)", "done": False})
                milestones.append({"key": "docker_image_pull", "label": "Docker image pulled", "done": False})
                milestones.append({"key": "docker_smoke_test", "label": "Docker image smoke test", "done": False})
            else:
                milestones.append({"key": "pr_agent_cloned", "label": "PR-Agent cloned & deps installed", "done": False})
            if has_ado:
                milestones.extend([
                    {"key": "ado_agent_download", "label": "Azure agent downloaded", "done": False},
                    {"key": "ado_agent_configured", "label": "Azure agent configured", "done": False},
                    {"key": "ado_agent_started", "label": "Azure agent service started", "done": False},
                ])
            milestones.append({"key": "startup_complete", "label": "Startup complete", "done": False})

            def mark(key: str) -> None:
                for m in milestones:
                    if m["key"] == key:
                        m["done"] = True
                        break

            if "installing docker ce" in c:
                mark("system_packages")
            if "docker installed." in c or "docker already installed." in c:
                mark("system_packages")
                mark("docker_ready")
                progress["docker_ready"] = True
            if "python and git installed." in c or "python and git already present." in c:
                mark("python_git_ready")
            if "env file written to /opt/pr-agent-runner/env." in c:
                mark("env_written")
                progress["env_written"] = True
            if "skipping pr-agent source clone" in c:
                mark("clone_skipped")
                progress["pr_agent_ready"] = True
            if "pr-agent clone and pip install done." in c or "pr-agent already present at /opt/pr-agent." in c:
                mark("pr_agent_cloned")
                progress["pr_agent_ready"] = True
            if "pulling docker image" in c or "docker image pulled successfully" in c:
                mark("docker_image_pull")
            if "docker smoke test passed" in c or "docker smoke test command failed" in c:
                mark("docker_smoke_test")
            if "downloading agent from" in c or "agent package downloaded" in c:
                mark("ado_agent_download")
            if "configuring agent" in c:
                mark("ado_agent_configured")
            if "registered in pool" in c:
                mark("ado_agent_started")
                progress["ado_agent_registered"] = True
            if "startup complete." in c:
                mark("startup_complete")
                progress["startup_complete"] = True

            if "fatal: startup script failed" in c or "self-destruct request sent" in c or "timeout:" in c:
                progress["failed"] = True
                progress["self_destructing"] = "self-destruct request sent" in c
                progress["timed_out"] = "timeout:" in c

            done_count = sum(1 for m in milestones if m["done"])
            progress["percent"] = min(100, int(done_count / len(milestones) * 100))
            progress["milestones"] = milestones

        except Exception:
            return progress
        return progress
