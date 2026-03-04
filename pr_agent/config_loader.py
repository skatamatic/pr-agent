import os
from os.path import abspath, dirname, join
from pathlib import Path
from typing import Optional

from dynaconf import Dynaconf
from starlette_context import context

PR_AGENT_TOML_KEY = 'pr-agent'

current_dir = dirname(abspath(__file__))

# Package-relative settings files (load order; later overrides earlier)
_PACKAGE_SETTINGS = [
    "settings/configuration.toml",
    "settings/ignore.toml",
    "settings/language_extensions.toml",
    "settings/pr_reviewer_prompts.toml",
    "settings/pr_questions_prompts.toml",
    "settings/pr_line_questions_prompts.toml",
    "settings/pr_description_prompts.toml",
    "settings/code_suggestions/pr_code_suggestions_prompts.toml",
    "settings/code_suggestions/pr_code_suggestions_prompts_not_decoupled.toml",
    "settings/code_suggestions/pr_code_suggestions_reflect_prompts.toml",
    "settings/pr_information_from_user_prompts.toml",
    "settings/pr_update_changelog_prompts.toml",
    "settings/pr_dev_time_estimation_prompts.toml",
    "settings/pr_custom_labels.toml",
    "settings/pr_add_docs.toml",
    "settings/custom_labels.toml",
    "settings/pr_help_prompts.toml",
    "settings/pr_help_docs_prompts.toml",
    "settings/pr_help_docs_headings_prompts.toml",
    "settings/csharp_code_context.config.toml",
    "settings/.secrets.toml",
    "settings_prod/.secrets.toml",
    "settings/csharp_code_context.secrets.toml",
]

# Files that may live in PR_AGENT_CONFIG_PATH or be downloaded from GCS (same names as dashboard uses)
_OVERLAY_FILENAMES = [
    "configuration.toml",
    "ignore.toml",
    ".secrets.toml",
    "csharp_code_context.config.toml",
    "csharp_code_context.secrets.toml",
]

# GCS object names (dashboard uses these; .secrets.toml is stored as secrets.toml in GCS)
_GCS_OBJECT_NAMES = [
    "configuration.toml",
    "ignore.toml",
    "secrets.toml",  # in GCS no leading dot
    "csharp_code_context.config.toml",
    "csharp_code_context.secrets.toml",
]


def _download_gcs_config_to_dir(bucket_name: str, prefix: str, target_dir: Path) -> None:
    """Download config objects from GCS to target_dir. Object 'secrets.toml' -> .secrets.toml on disk."""
    try:
        from google.cloud import storage
    except ImportError:
        return
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = prefix.rstrip("/") + "/" if prefix else ""
    target_dir.mkdir(parents=True, exist_ok=True)
    for gcs_name in _GCS_OBJECT_NAMES:
        blob = bucket.blob(prefix + gcs_name)
        if not blob.exists():
            continue
        content = blob.download_as_text(encoding="utf-8")
        # Map GCS name to local filename (secrets.toml -> .secrets.toml)
        local_name = ".secrets.toml" if gcs_name == "secrets.toml" else gcs_name
        (target_dir / local_name).write_text(content, encoding="utf-8")


def _get_overlay_dir() -> Optional[Path]:
    """Resolve overlay directory: PR_AGENT_CONFIG_PATH, or GCS download dir, or None."""
    path_env = os.getenv("PR_AGENT_CONFIG_PATH", "").strip()
    if path_env:
        return Path(path_env).resolve()
    bucket = os.getenv("PR_AGENT_CONFIG_GCS_BUCKET", "").strip()
    if not bucket:
        return None
    prefix = os.getenv("PR_AGENT_CONFIG_GCS_PREFIX", "pr-agent-config/").strip()
    cache_dir = os.getenv("PR_AGENT_CONFIG_CACHE_DIR", "").strip()
    if cache_dir:
        target = Path(cache_dir).resolve()
    else:
        import tempfile
        target = Path(tempfile.gettempdir()) / "pr_agent_config"
    _download_gcs_config_to_dir(bucket, prefix, target)
    return target


def _build_settings_files():
    """Package files first, then overlay from PR_AGENT_CONFIG_PATH or GCS so dashboard config wins."""
    files = [join(current_dir, f) for f in _PACKAGE_SETTINGS]
    overlay_path = _get_overlay_dir()
    if overlay_path:
        for name in _OVERLAY_FILENAMES:
            p = overlay_path / name
            if p.exists():
                files.append(str(p))
    return files


global_settings = Dynaconf(
    envvar_prefix=False,
    merge_enabled=True,
    settings_files=_build_settings_files(),
)


def get_settings(use_context=False):
    """
    Retrieves the current settings.

    This function attempts to fetch the settings from the starlette_context's context object. If it fails,
    it defaults to the global settings defined outside of this function.

    Returns:
        Dynaconf: The current settings object, either from the context or the global default.
    """
    try:
        return context["settings"]
    except Exception:
        return global_settings


# Add local configuration from pyproject.toml of the project being reviewed
def _find_repository_root() -> Optional[Path]:
    """
    Identify project root directory by recursively searching for the .git directory in the parent directories.
    """
    cwd = Path.cwd().resolve()
    no_way_up = False
    while not no_way_up:
        no_way_up = cwd == cwd.parent
        if (cwd / ".git").is_dir():
            return cwd
        cwd = cwd.parent
    return None


def _find_pyproject() -> Optional[Path]:
    """
    Search for file pyproject.toml in the repository root.
    """
    repo_root = _find_repository_root()
    if repo_root:
        pyproject = repo_root / "pyproject.toml"
        return pyproject if pyproject.is_file() else None
    return None


pyproject_path = _find_pyproject()
if pyproject_path is not None:
    get_settings().load_file(pyproject_path, env=f'tool.{PR_AGENT_TOML_KEY}')
