import os
from pathlib import Path
from typing import Dict

from dynaconf import Dynaconf

# Initialize Dynaconf with settings.toml
settings = Dynaconf(
    envvar_prefix="DASHBOARD",
    settings_files=["settings.toml"],
    environments=True,
    load_dotenv=True,
    merge_enabled=True,
)

# Set default values if not specified in settings.toml
if not hasattr(settings, 'app_name'):
    settings.app_name = "PR-Agent Dashboard"

if not hasattr(settings, 'debug'):
    settings.debug = False

if not hasattr(settings, 'log_level'):
    settings.log_level = "INFO"

if not hasattr(settings, 'log_format'):
    settings.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

if not hasattr(settings, 'api_host'):
    settings.api_host = "0.0.0.0"

if not hasattr(settings, 'api_port'):
    settings.api_port = int(os.getenv("PORT", os.getenv("DASHBOARD_API_PORT", "8000")))

# Cloud Run sets PORT; ensure we bind 0.0.0.0 when PORT is set (override production api_host if needed)
if os.getenv("PORT") and getattr(settings, "api_host", "") == "127.0.0.1":
    settings.api_host = "0.0.0.0"

if not hasattr(settings, 'developer_mode'):
    settings.developer_mode = True

if not hasattr(settings, 'database_url'):
    settings.database_url = "sqlite:///./dashboard.db"

if not hasattr(settings, 'database_echo'):
    settings.database_echo = False

if not hasattr(settings, 'cors_origins'):
    settings.cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
# GCP: allow comma-separated CORS origins from env (e.g. DASHBOARD_CORS_ORIGINS=https://app.run.app)
_cors_env = os.getenv("DASHBOARD_CORS_ORIGINS", "").strip()
if _cors_env:
    settings.cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]

# Optional API key for PR-Agent / programmatic access (env: DASHBOARD_API_KEY). If set, Bearer token can be this key instead of user JWT.
if not hasattr(settings, 'dashboard_api_key'):
    settings.dashboard_api_key = os.getenv("DASHBOARD_API_KEY", "").strip() or ""

# Log ingest limits (env: DASHBOARD_MAX_LOG_BATCH_ENTRIES, DASHBOARD_MAX_LOG_INGEST_BODY_BYTES)
if not hasattr(settings, 'max_log_batch_entries'):
    settings.max_log_batch_entries = int(os.getenv("DASHBOARD_MAX_LOG_BATCH_ENTRIES", "1000"))
if not hasattr(settings, 'max_log_ingest_body_bytes'):
    # Enforced when clients send Content-Length; pair with proxy body limits for chunked uploads.
    settings.max_log_ingest_body_bytes = int(os.getenv("DASHBOARD_MAX_LOG_INGEST_BODY_BYTES", str(5 * 1024 * 1024)))


def internal_log_ingest_headers() -> Dict[str, str]:
    """
    Authorization header dict for same-process HTTP calls to POST /logs/immediate|/logs/batch.

    When DASHBOARD_API_KEY is set, those routes require Bearer auth; without this, server-side
    self-logging would get 401 and silently skip persisting (requests does not raise on 4xx).

    Returns a new dict each call (safe to pass to requests / httpx). Empty key or whitespace-only
    yields {} so callers rely on JWT-only behavior when no machine key is configured.
    """
    raw = getattr(settings, "dashboard_api_key", None)
    if raw is None:
        key = ""
    else:
        key = str(raw).strip()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


# Base URLs for internal callbacks and frontend links (env: DASHBOARD_BACKEND_BASE_URL, DASHBOARD_FRONTEND_BASE_URL)
if not hasattr(settings, 'backend_base_url'):
    settings.backend_base_url = "http://localhost:8000"
if not hasattr(settings, 'frontend_base_url'):
    settings.frontend_base_url = "http://localhost:3000"

# PR-Agent integration paths - Use absolute paths to avoid working directory issues
def get_pr_agent_path():
    """Get the absolute path to PR-Agent directory"""
    # Get the directory containing this config file (dashboard/backend)
    config_dir = Path(__file__).parent
    # Go up two levels to get to pr-agent root (dashboard/backend -> dashboard -> pr-agent)
    pr_agent_root = config_dir.parent.parent
    return pr_agent_root

# Set absolute paths to avoid working directory dependencies
pr_agent_base = get_pr_agent_path()
settings.pr_agent_config_path = pr_agent_base / "pr_agent" / "settings" / "configuration.toml"
settings.pr_agent_backup_path = pr_agent_base / "pr_agent" / "settings" / "configuration.toml.backup"

# Additional TOML configuration files
settings.pr_agent_secrets_path = pr_agent_base / "pr_agent" / "settings" / "secrets.toml"
settings.pr_agent_ignore_path = pr_agent_base / "pr_agent" / "settings" / "ignore.toml"
settings.csharp_context_config_path = pr_agent_base / "pr_agent" / "settings" / "csharp_code_context.config.toml"
settings.csharp_context_secrets_path = pr_agent_base / "pr_agent" / "settings" / "csharp_code_context_secrets.toml"

# Create backup directory if it doesn't exist
if not settings.pr_agent_backup_path.parent.exists():
    settings.pr_agent_backup_path.parent.mkdir(parents=True, exist_ok=True)

# GCP Runner VM automation (optional). When set, dashboard can provision/deprovision runner VMs.
# GOOGLE_APPLICATION_CREDENTIALS or default SA for auth. Env: GCP_RUNNER_PROJECT_ID, GCP_RUNNER_REGION, etc.
if not hasattr(settings, 'gcp_runner_project_id'):
    settings.gcp_runner_project_id = os.getenv("GCP_RUNNER_PROJECT_ID", "").strip() or ""
if not hasattr(settings, 'gcp_runner_region'):
    settings.gcp_runner_region = os.getenv("GCP_RUNNER_REGION", "us-central1").strip()
if not hasattr(settings, 'gcp_runner_zone'):
    settings.gcp_runner_zone = os.getenv("GCP_RUNNER_ZONE", "").strip() or ""  # default region-a if empty
if not hasattr(settings, 'gcp_runner_machine_type'):
    settings.gcp_runner_machine_type = os.getenv("GCP_RUNNER_MACHINE_TYPE", "e2-medium").strip()
if not hasattr(settings, 'gcp_runner_subnet'):
    # Optional: full URL or short name (e.g. "default" or "projects/PROJECT/regions/REGION/subnetworks/NAME")
    settings.gcp_runner_subnet = os.getenv("GCP_RUNNER_SUBNET", "").strip() or ""
if not hasattr(settings, 'gcp_runner_network'):
    # Optional: full URL or short name (e.g. "default" or "projects/PROJECT/global/networks/NAME")
    settings.gcp_runner_network = os.getenv("GCP_RUNNER_NETWORK", "").strip() or ""
if not hasattr(settings, 'gcp_runner_prefix'):
    settings.gcp_runner_prefix = os.getenv("GCP_RUNNER_PREFIX", "pr-agent-runner").strip()
if not hasattr(settings, 'gcp_runner_pr_agent_repo_url'):
    settings.gcp_runner_pr_agent_repo_url = os.getenv("GCP_RUNNER_PR_AGENT_REPO_URL", "https://github.com/Codium-ai/pr-agent.git").strip()
if not hasattr(settings, 'gcp_runner_pr_agent_image'):
    settings.gcp_runner_pr_agent_image = os.getenv("GCP_RUNNER_PR_AGENT_IMAGE", "").strip()  # optional pre-pull, e.g. codiumai/pr-agent:0.23-github_action

# GCS config bucket/prefix (Terraform sets these on Cloud Run; used by dashboard for config and passed to runner VM startup script)
if not hasattr(settings, 'pr_agent_config_gcs_bucket'):
    settings.pr_agent_config_gcs_bucket = os.getenv("PR_AGENT_CONFIG_GCS_BUCKET", "").strip()
if not hasattr(settings, 'pr_agent_config_gcs_prefix'):
    _prefix = os.getenv("PR_AGENT_CONFIG_GCS_PREFIX", "pr-agent-config/").strip()
    settings.pr_agent_config_gcs_prefix = _prefix if _prefix else "pr-agent-config/"

# Legacy compatibility - keep dashboard_config for backward compatibility
dashboard_config = settings 