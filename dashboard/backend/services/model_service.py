"""Dashboard service for LLM model discovery and benchmarking."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pr_agent.algo.model_discovery import discover_models_async
from pr_agent.algo.model_test import run_model_benchmark

from .config_backend import CONFIG_KEY, SECRETS_KEY


class ModelService:
    CACHE_TTL_SECONDS = 600

    def __init__(self, config_service):
        self.config_service = config_service
        self._cache: Dict[str, Any] = {}

    def clear_cache(self) -> None:
        """Drop cached discovery results (e.g. after API keys are saved)."""
        self._cache.clear()

    def _cache_key(self, secrets: Dict[str, Any], openai_config: Dict[str, Any]) -> str:
        payload = {
            "openai": bool((secrets.get("openai") or {}).get("key")),
            "anthropic": bool((secrets.get("anthropic") or {}).get("key")),
            "google": bool((secrets.get("google_ai_studio") or {}).get("gemini_api_key")),
            "openrouter": bool((secrets.get("openrouter") or {}).get("key")),
            "azure": (openai_config.get("api_type") or "").lower() == "azure",
            "api_base": openai_config.get("api_base") or "",
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _load_secrets_config(self) -> Dict[str, Any]:
        return self.config_service._load_toml_from_backend(SECRETS_KEY) or {}

    def _load_main_config(self) -> Dict[str, Any]:
        return self.config_service._load_toml_from_backend(CONFIG_KEY) or {}

    def _build_secrets_dict(
        self,
        secrets_config: Optional[Dict[str, Any]] = None,
        api_keys_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        secrets_config = secrets_config or self._load_secrets_config()
        api_keys_override = api_keys_override or {}

        def _read(section: str, field: str, override_key: str) -> str:
            override_val = (api_keys_override.get(override_key) or "").strip()
            if override_val and override_val != "***":
                return override_val
            section_val = secrets_config.get(section) or {}
            if isinstance(section_val, dict):
                return (section_val.get(field) or "").strip()
            return ""

        secrets: Dict[str, Any] = {}

        openai_key = _read("openai", "key", "openai")
        openai_section = secrets_config.get("openai") if isinstance(secrets_config.get("openai"), dict) else {}
        openai_payload: Dict[str, Any] = dict(openai_section or {})
        if openai_key:
            openai_payload["key"] = openai_key
        if openai_payload.get("key"):
            secrets["openai"] = openai_payload

        anthropic_key = _read("anthropic", "key", "anthropic")
        if anthropic_key:
            secrets["anthropic"] = {"key": anthropic_key}

        google_key = _read("google_ai_studio", "gemini_api_key", "google")
        if google_key:
            secrets["google_ai_studio"] = {"gemini_api_key": google_key}

        openrouter_section = secrets_config.get("openrouter") if isinstance(secrets_config.get("openrouter"), dict) else {}
        openrouter_key = _read("openrouter", "key", "openrouter")
        if openrouter_key or openrouter_section:
            secrets["openrouter"] = {**openrouter_section, **({"key": openrouter_key} if openrouter_key else {})}

        return secrets

    def _build_openai_config(
        self,
        main_config: Optional[Dict[str, Any]] = None,
        secrets_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        main_config = main_config or self._load_main_config()
        secrets_config = secrets_config or self._load_secrets_config()
        openai_section = {}
        if isinstance(secrets_config.get("openai"), dict):
            openai_section.update(secrets_config["openai"])
        if isinstance(main_config.get("openai"), dict):
            openai_section.update(main_config["openai"])
        return {
            "api_type": openai_section.get("api_type") or openai_section.get("API_TYPE") or "",
            "api_base": openai_section.get("api_base") or openai_section.get("API_BASE") or "",
            "api_version": openai_section.get("api_version") or openai_section.get("API_VERSION") or "2024-02-01",
        }

    async def discover_models(self, force_refresh: bool = False) -> Dict[str, Any]:
        secrets_config = self._load_secrets_config()
        main_config = self._load_main_config()
        secrets = self._build_secrets_dict(secrets_config)
        openai_config = self._build_openai_config(main_config, secrets_config)
        cache_key = self._cache_key(secrets, openai_config)

        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and not force_refresh and (now - cached["stored_at"]) < self.CACHE_TTL_SECONDS:
            return cached["payload"]

        result = await discover_models_async(secrets=secrets, openai_config=openai_config)
        payload = result.to_dict()
        payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
        self._cache[cache_key] = {"stored_at": now, "payload": payload}
        return payload

    async def test_model(
        self,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        use_saved_config: bool = True,
    ) -> Dict[str, Any]:
        model = (model or "").strip()
        if not model:
            return {"success": False, "model": "", "error": "Model is required"}

        secrets_config = self._load_secrets_config() if use_saved_config else {}
        effective_keys = api_keys or {}
        secrets = self._build_secrets_dict(secrets_config, api_keys_override=effective_keys)

        result = await run_model_benchmark(model, secrets=secrets)
        return result.to_dict()
