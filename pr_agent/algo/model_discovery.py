"""Discover chat models from configured providers and LiteLLM catalog."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from pr_agent.log import get_logger

_LITELLM_CHAT_CACHE: Optional[List["DiscoveredModel"]] = None
_LITELLM_CHAT_CACHE_AT: float = 0.0
_LITELLM_CHAT_CACHE_TTL_SECONDS = 3600

_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "azure": "Azure OpenAI",
    "openrouter": "OpenRouter",
    "litellm": "LiteLLM",
}

_SPECIALTY_NAME_PATTERNS = (
    r"embed",
    r"embedding",
    r"whisper",
    r"tts",
    r"dall-e",
    r"dalle",
    r"transcribe",
    r"moderation",
    r"rerank",
    r"audio",
    r"vision-preview",
    r"text-embedding",
    r"imagen",
    r"veo",
)

_OPENAI_NON_CHAT_PREFIXES = (
    "text-embedding",
    "whisper",
    "tts",
    "dall-e",
    "davinci",
    "babbage",
    "curie",
    "ada",
    "omni-moderation",
)


@dataclass
class DiscoveredModel:
    id: str
    display_name: str
    provider: str
    source: str
    max_input_tokens: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryResult:
    providers: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    all_ids: List[str] = field(default_factory=list)
    provider_errors: Dict[str, str] = field(default_factory=dict)
    provider_status: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "providers": self.providers,
            "all_ids": self.all_ids,
            "provider_errors": self.provider_errors,
            "provider_status": self.provider_status,
        }


def is_specialty_model(model_id: str) -> bool:
    """Return True if model id looks like embedding/vision/audio/etc."""
    normalized = model_id.lower().split("/")[-1]
    for prefix in _OPENAI_NON_CHAT_PREFIXES:
        if normalized.startswith(prefix):
            return True
    for pattern in _SPECIALTY_NAME_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return False


def _litellm_chat_models() -> List[DiscoveredModel]:
    global _LITELLM_CHAT_CACHE, _LITELLM_CHAT_CACHE_AT
    now = time.time()
    if _LITELLM_CHAT_CACHE is not None and (now - _LITELLM_CHAT_CACHE_AT) < _LITELLM_CHAT_CACHE_TTL_SECONDS:
        return list(_LITELLM_CHAT_CACHE)

    try:
        import litellm
    except ImportError:
        return []

    models: List[DiscoveredModel] = []
    for model_id in litellm.model_list:
        if is_specialty_model(model_id):
            continue
        try:
            info = litellm.get_model_info(model_id)
        except Exception:
            continue
        if info.get("mode") and info.get("mode") != "chat":
            continue
        provider = _provider_from_litellm_id(model_id)
        max_tokens = info.get("max_input_tokens")
        models.append(
            DiscoveredModel(
                id=model_id,
                display_name=model_id.split("/")[-1],
                provider=provider,
                source="litellm",
                max_input_tokens=max_tokens if isinstance(max_tokens, int) else None,
            )
        )
    _LITELLM_CHAT_CACHE = models
    _LITELLM_CHAT_CACHE_AT = now
    return list(models)


def reset_litellm_chat_cache_for_tests() -> None:
    global _LITELLM_CHAT_CACHE, _LITELLM_CHAT_CACHE_AT
    _LITELLM_CHAT_CACHE = None
    _LITELLM_CHAT_CACHE_AT = 0.0


def _provider_from_litellm_id(model_id: str) -> str:
    if model_id.startswith("anthropic/"):
        return "anthropic"
    if model_id.startswith("gemini/") or model_id.startswith("vertex_ai/"):
        return "google"
    if model_id.startswith("azure/"):
        return "azure"
    if model_id.startswith("openrouter/"):
        return "openrouter"
    # Some LiteLLM catalog entries are bare model names without a provider prefix
    # (e.g. "claude-3-5-haiku-latest", "gemini-1.5-pro"). Classify by family so they
    # land under the correct provider group instead of defaulting to OpenAI.
    normalized = model_id.lower().split("/")[-1]
    if "claude" in normalized:
        return "anthropic"
    if normalized.startswith("gemini") or normalized.startswith("palm"):
        return "google"
    return "openai"


def _extract_provider_keys(secrets: Dict[str, Any], openai_config: Dict[str, Any]) -> Dict[str, str]:
    """Return provider -> key for providers that have credentials configured."""
    keys: Dict[str, str] = {}

    openai_key = (secrets.get("openai") or {}).get("key") or secrets.get("openai_key") or ""
    anthropic_key = (secrets.get("anthropic") or {}).get("key") or secrets.get("anthropic_key") or ""
    google_key = (
        (secrets.get("google_ai_studio") or {}).get("gemini_api_key")
        or secrets.get("google_key")
        or ""
    )
    openrouter_key = (secrets.get("openrouter") or {}).get("key") or secrets.get("openrouter_key") or ""

    api_type = (openai_config.get("api_type") or openai_config.get("API_TYPE") or "").lower()
    api_base = openai_config.get("api_base") or openai_config.get("API_BASE") or ""

    if openai_key and api_type == "azure" and api_base:
        keys["azure"] = openai_key
    elif openai_key:
        keys["openai"] = openai_key
    if anthropic_key:
        keys["anthropic"] = anthropic_key
    if google_key:
        keys["google"] = google_key
    if openrouter_key:
        keys["openrouter"] = openrouter_key
    return keys


def _filter_models_for_providers(
    models: Sequence[DiscoveredModel],
    allowed_providers: set[str],
) -> List[DiscoveredModel]:
    if not allowed_providers:
        return []
    return [model for model in models if model.provider in allowed_providers]


def _merge_models(live: Sequence[DiscoveredModel], fallback: Sequence[DiscoveredModel]) -> DiscoveryResult:
    by_id: Dict[str, DiscoveredModel] = {}
    for model in live:
        by_id[model.id] = model
    for model in fallback:
        if model.id not in by_id:
            by_id[model.id] = model

    providers: Dict[str, List[Dict[str, Any]]] = {}
    for model in by_id.values():
        label = _PROVIDER_LABELS.get(model.provider, model.provider.title())
        providers.setdefault(label, []).append(model.to_dict())

    for label in providers:
        providers[label].sort(key=lambda m: (m.get("source") != "live", m["id"]))

    all_ids = sorted(by_id.keys(), key=lambda mid: (by_id[mid].source != "live", mid))
    return DiscoveryResult(providers=providers, all_ids=all_ids)


async def _fetch_openai_models(api_key: str, timeout: float = 15.0) -> List[DiscoveredModel]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()

    models: List[DiscoveredModel] = []
    for item in payload.get("data", []):
        model_id = item.get("id", "")
        if not model_id or is_specialty_model(model_id):
            continue
        models.append(
            DiscoveredModel(
                id=model_id,
                display_name=model_id,
                provider="openai",
                source="live",
            )
        )
    return models


_ANTHROPIC_PAGE_SIZE = 100
_ANTHROPIC_MAX_PAGES = 50


async def _fetch_anthropic_models(api_key: str, timeout: float = 15.0) -> List[DiscoveredModel]:
    """Fetch all Anthropic chat models, walking through every page of results.

    The Anthropic /v1/models endpoint paginates (default 20, max 1000 per page) and
    returns `has_more`/`last_id` cursors. We page through several pages explicitly so
    newly released models (e.g. Haiku) are never truncated by a single page.
    """
    models: List[DiscoveredModel] = []
    seen_ids: set[str] = set()
    async with httpx.AsyncClient(timeout=timeout) as client:
        after_id: Optional[str] = None
        for _ in range(_ANTHROPIC_MAX_PAGES):
            params: Dict[str, Any] = {"limit": _ANTHROPIC_PAGE_SIZE}
            if after_id:
                params["after_id"] = after_id
            response = await client.get(
                "https://api.anthropic.com/v1/models",
                params=params,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
            response.raise_for_status()
            payload = response.json()

            data = payload.get("data") or []
            for item in data:
                model_id = item.get("id", "")
                if not model_id or model_id in seen_ids or is_specialty_model(model_id):
                    continue
                seen_ids.add(model_id)
                litellm_id = model_id if model_id.startswith("anthropic/") else f"anthropic/{model_id}"
                models.append(
                    DiscoveredModel(
                        id=litellm_id,
                        display_name=item.get("display_name") or model_id,
                        provider="anthropic",
                        source="live",
                        max_input_tokens=item.get("max_input_tokens")
                        if isinstance(item.get("max_input_tokens"), int)
                        else None,
                    )
                )

            if not payload.get("has_more"):
                break
            after_id = payload.get("last_id")
            if not after_id:
                break
    return models


async def _fetch_gemini_models(api_key: str, timeout: float = 15.0) -> List[DiscoveredModel]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
        response.raise_for_status()
        payload = response.json()

    models: List[DiscoveredModel] = []
    for item in payload.get("models", []):
        name = item.get("name", "")
        model_id = name.split("/")[-1] if name else ""
        if not model_id or is_specialty_model(model_id):
            continue
        supported = item.get("supportedGenerationMethods") or []
        if supported and "generateContent" not in supported:
            continue
        litellm_id = f"gemini/{model_id}"
        models.append(
            DiscoveredModel(
                id=litellm_id,
                display_name=model_id,
                provider="google",
                source="live",
            )
        )
    return models


async def _fetch_azure_deployments(
    api_key: str,
    api_base: str,
    api_version: str = "2024-02-01",
    timeout: float = 15.0,
) -> List[DiscoveredModel]:
    base = api_base.rstrip("/")
    url = f"{base}/openai/deployments"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            url,
            params={"api-version": api_version},
            headers={"api-key": api_key},
        )
        response.raise_for_status()
        payload = response.json()

    models: List[DiscoveredModel] = []
    for item in payload.get("data", []):
        deployment = item.get("id") or item.get("name") or ""
        if not deployment:
            continue
        models.append(
            DiscoveredModel(
                id=f"azure/{deployment}",
                display_name=deployment,
                provider="azure",
                source="live",
            )
        )
    return models


async def _fetch_openrouter_models(api_key: str, timeout: float = 15.0) -> List[DiscoveredModel]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()

    models: List[DiscoveredModel] = []
    for item in payload.get("data", []):
        model_id = item.get("id", "")
        if not model_id or is_specialty_model(model_id):
            continue
        models.append(
            DiscoveredModel(
                id=model_id,
                display_name=item.get("name") or model_id,
                provider="openrouter",
                source="live",
            )
        )
    return models


async def discover_models_async(
    secrets: Optional[Dict[str, Any]] = None,
    openai_config: Optional[Dict[str, Any]] = None,
    include_litellm_fallback: bool = True,
) -> DiscoveryResult:
    """
    Discover chat models from live provider APIs (when keys exist) plus LiteLLM catalog fallback.
    """
    secrets = secrets or {}
    openai_config = openai_config or {}
    live_models: List[DiscoveredModel] = []
    provider_errors: Dict[str, str] = {}
    provider_status: Dict[str, str] = {}

    provider_keys = _extract_provider_keys(secrets, openai_config)
    configured_providers = set(provider_keys.keys())

    tasks: Dict[str, Any] = {}

    api_type = (openai_config.get("api_type") or openai_config.get("API_TYPE") or "").lower()
    api_base = openai_config.get("api_base") or openai_config.get("API_BASE") or ""
    api_version = openai_config.get("api_version") or openai_config.get("API_VERSION") or "2024-02-01"

    if "azure" in provider_keys:
        provider_status["azure"] = "configured"
        tasks["azure"] = _fetch_azure_deployments(provider_keys["azure"], api_base, api_version)
    else:
        provider_status["azure"] = "no_key"

    if "openai" in provider_keys:
        provider_status["openai"] = "configured"
        tasks["openai"] = _fetch_openai_models(provider_keys["openai"])
    else:
        provider_status["openai"] = "no_key"

    if "anthropic" in provider_keys:
        provider_status["anthropic"] = "configured"
        tasks["anthropic"] = _fetch_anthropic_models(provider_keys["anthropic"])
    else:
        provider_status["anthropic"] = "no_key"

    if "google" in provider_keys:
        provider_status["google"] = "configured"
        tasks["google"] = _fetch_gemini_models(provider_keys["google"])
    else:
        provider_status["google"] = "no_key"

    if "openrouter" in provider_keys:
        provider_status["openrouter"] = "configured"
        tasks["openrouter"] = _fetch_openrouter_models(provider_keys["openrouter"])
    else:
        provider_status["openrouter"] = "no_key"

    if tasks:
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for provider_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                provider_errors[provider_name] = str(result)
                get_logger().warning(f"Model discovery failed for {provider_name}: {result}")
            else:
                live_models.extend(result)

    fallback: List[DiscoveredModel] = []
    if include_litellm_fallback and configured_providers:
        fallback = _filter_models_for_providers(_litellm_chat_models(), configured_providers)

    merged = _merge_models(live_models, fallback)
    merged.provider_errors = provider_errors
    merged.provider_status = provider_status
    return merged


def discover_models(
    secrets: Optional[Dict[str, Any]] = None,
    openai_config: Optional[Dict[str, Any]] = None,
    include_litellm_fallback: bool = True,
) -> DiscoveryResult:
    """Synchronous wrapper for discover_models_async."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                discover_models_async(secrets, openai_config, include_litellm_fallback),
            )
            return future.result()
    return asyncio.run(discover_models_async(secrets, openai_config, include_litellm_fallback))
