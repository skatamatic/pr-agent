"""Apply LiteLLM provider credentials from explicit secret dicts (dashboard benchmarks)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import litellm


def _snapshot_litellm_state() -> Dict[str, Any]:
    return {
        "openai_key": getattr(litellm, "openai_key", None),
        "anthropic_key": getattr(litellm, "anthropic_key", None),
        "azure_key": getattr(litellm, "azure_key", None),
        "api_key": getattr(litellm, "api_key", None),
        "api_base": getattr(litellm, "api_base", None),
        "api_version": getattr(litellm, "api_version", None),
        "organization": getattr(litellm, "organization", None),
    }


def _restore_litellm_state(state: Dict[str, Any]) -> None:
    for key, value in state.items():
        setattr(litellm, key, value)


def _snapshot_env(keys: tuple[str, ...]) -> Dict[str, Optional[str]]:
    return {key: os.environ.get(key) for key in keys}


def _restore_env(snapshot: Dict[str, Optional[str]]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def apply_litellm_credentials_from_secrets(secrets: Dict[str, Any]) -> None:
    """Configure litellm module globals and env vars from a secrets-shaped dict."""
    openai_section = secrets.get("openai") or {}
    if isinstance(openai_section, dict):
        openai_key = (openai_section.get("key") or "").strip()
        if openai_key:
            litellm.openai_key = openai_key
            os.environ["OPENAI_API_KEY"] = openai_key
        api_type = (openai_section.get("api_type") or openai_section.get("API_TYPE") or "").lower()
        api_base = openai_section.get("api_base") or openai_section.get("API_BASE") or ""
        api_version = openai_section.get("api_version") or openai_section.get("API_VERSION") or ""
        if api_type == "azure":
            litellm.azure_key = openai_key
            if api_base:
                litellm.api_base = api_base
                os.environ["AZURE_API_BASE"] = api_base
            if api_version:
                litellm.api_version = api_version
                os.environ["AZURE_API_VERSION"] = api_version
        elif api_base:
            litellm.api_base = api_base

    anthropic_section = secrets.get("anthropic") or {}
    if isinstance(anthropic_section, dict):
        anthropic_key = (anthropic_section.get("key") or "").strip()
        if anthropic_key:
            litellm.anthropic_key = anthropic_key
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key

    google_section = secrets.get("google_ai_studio") or {}
    if isinstance(google_section, dict):
        gemini_key = (google_section.get("gemini_api_key") or "").strip()
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key

    openrouter_section = secrets.get("openrouter") or {}
    if isinstance(openrouter_section, dict):
        openrouter_key = (openrouter_section.get("key") or "").strip()
        if openrouter_key:
            litellm.api_key = openrouter_key
            os.environ["OPENROUTER_API_KEY"] = openrouter_key
        openrouter_base = openrouter_section.get("api_base") or openrouter_section.get("API_BASE") or ""
        if openrouter_base:
            litellm.api_base = openrouter_base
            os.environ["OPENROUTER_API_BASE"] = openrouter_base


@contextmanager
def temporary_litellm_credentials(
    secrets: Optional[Dict[str, Any]] = None,
) -> Iterator[None]:
    """Temporarily apply provider credentials for a single LiteLLM call."""
    env_keys = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_BASE",
        "AZURE_API_BASE",
        "AZURE_API_VERSION",
    )
    litellm_snapshot = _snapshot_litellm_state()
    env_snapshot = _snapshot_env(env_keys)
    try:
        if secrets:
            apply_litellm_credentials_from_secrets(secrets)
        yield
    finally:
        _restore_litellm_state(litellm_snapshot)
        _restore_env(env_snapshot)
