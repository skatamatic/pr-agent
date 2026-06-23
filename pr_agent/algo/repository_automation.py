"""Apply per-repository automation flags from the PR-Agent dashboard."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

try:
    from pr_agent.log.job_context import extract_repository_from_url
    from pr_agent.log.dashboard_client import DashboardClient
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False
    extract_repository_from_url = None  # type: ignore
    DashboardClient = None  # type: ignore

_AUTO_ENV_KEYS = (
    "AZURE_DEVOPS_CONFIG.AUTO_DESCRIBE",
    "AZURE_DEVOPS_CONFIG.AUTO_REVIEW",
    "AZURE_DEVOPS_CONFIG.AUTO_IMPROVE",
    "GITHUB_ACTION_CONFIG.AUTO_DESCRIBE",
    "GITHUB_ACTION_CONFIG.AUTO_REVIEW",
    "GITHUB_ACTION_CONFIG.AUTO_IMPROVE",
)


def _env_var_is_set(key: str) -> bool:
    candidates = {key, key.upper(), key.lower(), key.replace(".", "__"), key.replace(".", "_")}
    return any(os.getenv(name) not in (None, "") for name in candidates)


def _automation_env_overrides_active() -> bool:
    return any(_env_var_is_set(key) for key in _AUTO_ENV_KEYS)


def _repo_settings_has_key(repo_settings: Optional[Dict[str, Any]], section: str, field: str) -> bool:
    if not isinstance(repo_settings, dict):
        return False
    for section_name in (section, section.upper()):
        section_data = repo_settings.get(section_name)
        if not isinstance(section_data, dict):
            continue
        for field_name in (field, field.upper()):
            if field_name in section_data:
                return True
    return False


def _set_automation_flag(section: str, field: str, value: bool) -> None:
    dotted = f"{section}.{field}".upper()
    get_settings().set(dotted, value)


async def _fetch_dashboard_automation(repository_name: str) -> Optional[Dict[str, bool]]:
    if not DASHBOARD_AVAILABLE or DashboardClient is None:
        return None
    client = DashboardClient()
    try:
        response = await client.get_repository_automation_settings(repository_name)
        if not response:
            return None
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            return None
        return {
            "auto_describe": bool(data.get("auto_describe", True)),
            "auto_review": bool(data.get("auto_review", True)),
            "auto_improve": bool(data.get("auto_improve", False)),
        }
    except Exception as exc:
        get_logger().debug(f"Failed to fetch dashboard repository automation: {exc}")
        return None
    finally:
        await client.close()


def apply_dashboard_repository_automation(
    pr_url: str,
    repo_settings: Optional[Dict[str, Any]] = None,
) -> None:
    """Apply dashboard repository auto_* flags unless pipeline env or repo TOML already set them."""
    if not DASHBOARD_AVAILABLE or extract_repository_from_url is None:
        return
    if _automation_env_overrides_active():
        get_logger().debug("Skipping dashboard repository automation; pipeline env vars are set")
        return

    repository_name = extract_repository_from_url(pr_url)
    if not repository_name:
        return

    try:
        automation = asyncio.run(_fetch_dashboard_automation(repository_name))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            automation = loop.run_until_complete(_fetch_dashboard_automation(repository_name))
        finally:
            loop.close()
    except Exception as exc:
        get_logger().debug(f"Dashboard repository automation lookup failed: {exc}")
        return

    if not automation:
        return

    mapping = (
        ("azure_devops_config", "auto_describe", automation["auto_describe"]),
        ("azure_devops_config", "auto_review", automation["auto_review"]),
        ("azure_devops_config", "auto_improve", automation["auto_improve"]),
        ("github_action_config", "auto_describe", automation["auto_describe"]),
        ("github_action_config", "auto_review", automation["auto_review"]),
        ("github_action_config", "auto_improve", automation["auto_improve"]),
    )
    for section, field, value in mapping:
        if _repo_settings_has_key(repo_settings, section, field):
            continue
        _set_automation_flag(section, field, value)

    get_logger().info(
        "Applied dashboard repository automation settings",
        artifact={"repository": repository_name, **automation},
    )
