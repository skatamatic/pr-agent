"""
GCP Runner VM service: provision and deprovision Compute Engine VMs for self-hosted
GitHub Actions / Azure DevOps runners. Used when a repo is connected via a runner connection
and the dashboard is configured for GCP (GCP_RUNNER_PROJECT_ID, etc.).
"""
import logging
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Optional: only required when GCP runner provisioning is used
try:
    from google.cloud import compute_v1
    GCP_COMPUTE_AVAILABLE = True
except ImportError:
    GCP_COMPUTE_AVAILABLE = False
    compute_v1 = None


def _safe_instance_name(name: str) -> str:
    """GCE instance names must match [a-z]([-a-z0-9]*[a-z0-9])? (RFC 1035, 1-63 chars)."""
    s = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    if not s or not s[0].isalpha():
        s = "r-" + s
    s = s[:63].rstrip("-")
    return s or "runner"


def _get_startup_script(
    dashboard_url: str,
    config_bucket: str = "",
    config_prefix: str = "pr-agent-config/",
    pr_agent_repo_url: str = "https://github.com/Codium-ai/pr-agent.git",
    pr_agent_image: str = "",
) -> str:
    """Build startup script equivalent to terraform/gcp/runner-startup.sh.tpl.
    Keep in sync: same sections, env vars, and optional pre-pull block."""
    pre_pull_block = ""
    if pr_agent_image:
        ar_auth_block = ""
        if "docker.pkg.dev" in pr_agent_image:
            ar_auth_block = f"""
# Authenticate Docker with Artifact Registry (GCE metadata token)
log "Authenticating Docker with Artifact Registry..."
_AR_REGISTRY=$(echo "{pr_agent_image}" | cut -d/ -f1)
_AR_TOKEN=$(curl -s -H "Metadata-Flavor: Google" \\
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "$_AR_TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$_AR_REGISTRY" 2>/dev/null \\
  && log "Docker authenticated with $_AR_REGISTRY." \\
  || log "Docker auth failed (non-fatal); pull may still fail."
"""
        pre_pull_block = f"""{ar_auth_block}
if ! docker image inspect "{pr_agent_image}" &>/dev/null; then
  log "Pre-pulling Docker image: {pr_agent_image}"
  docker pull "{pr_agent_image}" || log "Pre-pull failed (non-fatal); first job will pull."
else
  log "Docker image {pr_agent_image} already present."
fi
"""
    return f"""#!/bin/bash
# Runner VM startup: Docker, Python, pr-agent clone, env file. Idempotent; logs to stdout.
set -e
export DEBIAN_FRONTEND=noninteractive

log() {{ echo "[pr-agent-runner-startup] $*"; }}

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
export DASHBOARD_URL="{dashboard_url}"
export PR_AGENT_CONFIG_GCS_BUCKET="{config_bucket}"
export PR_AGENT_CONFIG_GCS_PREFIX="{config_prefix}"
ENVEOF
chmod 644 /opt/pr-agent-runner/env
log "Env file written to /opt/pr-agent-runner/env."

# --- Clone PR-Agent for Python-from-clone execution (e.g. Azure Pipelines) ---
PR_AGENT_DIR=/opt/pr-agent
if [ ! -d "$PR_AGENT_DIR/.git" ]; then
  log "Cloning PR-Agent into $PR_AGENT_DIR..."
  git clone --depth 1 "{pr_agent_repo_url}" "$PR_AGENT_DIR"
  pip3 install -r "$PR_AGENT_DIR/requirements.txt" --break-system-packages 2>/dev/null || pip3 install -r "$PR_AGENT_DIR/requirements.txt"
  log "PR-Agent clone and pip install done."
else
  log "PR-Agent already present at $PR_AGENT_DIR."
fi
{pre_pull_block}
# --- Verify ---
docker --version && log "Startup complete. Install ADO/GitHub agent; use Docker (e.g. uses: docker://codiumai/pr-agent:...) or Python from $PR_AGENT_DIR with env from /opt/pr-agent-runner/env."
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
        name_prefix: str = "pr-agent-runner",
        dashboard_url: str = "",
        config_bucket: str = "",
        config_prefix: str = "pr-agent-config/",
        pr_agent_repo_url: str = "https://github.com/Codium-ai/pr-agent.git",
        pr_agent_runner_image: str = "",
    ):
        self.project_id = project_id
        self.region = region
        self.zone = zone or f"{region}-a"
        self.machine_type = machine_type
        self.subnet = subnet
        self.name_prefix = name_prefix
        self.dashboard_url = dashboard_url
        self.config_bucket = config_bucket
        self.config_prefix = config_prefix
        self.pr_agent_repo_url = pr_agent_repo_url
        self.pr_agent_runner_image = pr_agent_runner_image or ""
        self._client: Optional[Any] = None

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
    ) -> Dict[str, Any]:
        """
        Create a GCE VM for this runner connection. Returns dict with instance_name, zone,
        status, message, and install_instructions for the user (copy-paste runner install).
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "GCP runner not configured. Set GCP_RUNNER_PROJECT_ID and GCP_RUNNER_REGION (and optionally GCP_RUNNER_ZONE).",
                "instance_name": None,
                "zone": None,
            }
        name = self.instance_name_for_connection(connection_id, provider, organization, project)
        try:
            startup_script = _get_startup_script(
                dashboard_url=self.dashboard_url,
                config_bucket=self.config_bucket,
                config_prefix=self.config_prefix,
                pr_agent_repo_url=self.pr_agent_repo_url,
                pr_agent_image=self.pr_agent_runner_image,
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
                if self.subnet.startswith("http") or "/subnetworks/" in self.subnet:
                    network_interface.subnetwork = self.subnet
                else:
                    network_interface.subnetwork = f"projects/{self.project_id}/regions/{self.region}/subnetworks/{self.subnet}"
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
            install_instructions = self._install_instructions(provider, name)
            return {
                "success": True,
                "instance_name": name,
                "zone": self.zone,
                "message": "VM creation started. It may take 1–2 minutes to be running. Use the instructions below to install the runner/agent on the VM.",
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

    def _install_instructions(self, provider: str, instance_name: str) -> Dict[str, str]:
        """Short copy-paste instructions for ADO or GitHub runner install and PR-Agent execution (Docker vs Python)."""
        ssh_hint = f"gcloud compute ssh {instance_name} --zone={self.zone} --project={self.project_id}"
        gcs_note = " For Docker: pass PR_AGENT_CONFIG_GCS_BUCKET and PR_AGENT_CONFIG_GCS_PREFIX (same as in /opt/pr-agent-runner/env) so the container loads config from the same GCS bucket as the dashboard."
        image_note = f" Pre-pulled image on this VM: {self.pr_agent_runner_image}." if self.pr_agent_runner_image else ""
        common_pr_agent = (
            " PR-Agent: VM has Docker and a clone at /opt/pr-agent. Use workflow step 'uses: docker://...' with your image (e.g. " + (self.pr_agent_runner_image or "codiumai/pr-agent:VERSION-github_action") + ") or run Python: source /opt/pr-agent-runner/env && python3 /opt/pr-agent/pr_agent/servers/<runner_script>.py. Pass OPENAI_KEY, DASHBOARD_URL, DASHBOARD_API_KEY, and GITHUB_TOKEN or Azure vars."
            + gcs_note + image_note + " See docs/RUNNER_VM_AND_PR_AGENT_FLOW.md."
        )
        if provider == "github":
            return {
                "ssh_command": ssh_hint,
                "steps": "1. SSH to the VM (see ssh_command). 2. Follow GitHub: Settings > Actions > Runners > New self-hosted runner; copy-paste the install script. 3. In workflows, use Docker (e.g. uses: docker://IMAGE) or run Python from /opt/pr-agent; set env DASHBOARD_URL, OPENAI_API_KEY, DASHBOARD_API_KEY, GITHUB_TOKEN, PR_AGENT_CONFIG_GCS_BUCKET, PR_AGENT_CONFIG_GCS_PREFIX."
                + common_pr_agent,
                "docs_url": "https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners",
            }
        if provider == "azure_devops":
            return {
                "ssh_command": ssh_hint,
                "steps": "1. SSH to the VM (see ssh_command). 2. In Azure DevOps: Project settings > Agent pools > Add agent > Linux; run the registration script on the VM. 3. In pipeline steps, source /opt/pr-agent-runner/env (sets DASHBOARD_URL and GCS config) and run python3 /opt/pr-agent/pr_agent/servers/azuredevops_pipeline_runner.py; set pipeline variables (OPENAI_API_KEY, DASHBOARD_API_KEY, etc.)."
                + common_pr_agent,
                "docs_url": "https://learn.microsoft.com/en-us/azure/devops/pipelines/agents/linux-agent",
            }
        return {"ssh_command": ssh_hint, "steps": "SSH to the VM and install the runner/agent per your provider docs." + common_pr_agent, "docs_url": ""}

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
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                return {"success": True, "message": "Instance already deleted or not found."}
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
