from pathlib import Path
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
    settings.api_port = 8000

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

# Legacy compatibility - keep dashboard_config for backward compatibility
dashboard_config = settings 