"""Dynamic model token limits and capability resolution."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from pr_agent.algo import (
    CLAUDE_EXTENDED_THINKING_MODELS,
    MAX_TOKENS,
    SUPPORT_REASONING_EFFORT_MODELS,
    USER_MESSAGE_ONLY_MODELS,
)
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

DEFAULT_MAX_INPUT_TOKENS = 128000

_NO_TEMPERATURE_PATTERNS = (
    r"^o1(-|$)",
    r"^o3(-|$)",
    r"^o4(-|$)",
    r"deepseek/deepseek-reasoner",
    r"deepseek-reasoner",
)
_REASONING_PATTERNS = (
    r"^o1(-|$)",
    r"^o3(-|$)",
    r"^o4(-|$)",
    r"^gpt-5",
    r"reasoner",
)
_USER_MESSAGE_ONLY_PATTERNS = (
    r"deepseek/deepseek-reasoner",
    r"deepseek-reasoner",
    r"^o1-mini",
    r"^o1-preview",
)


def _normalize_model_id(model: str) -> str:
    return model.removeprefix("azure/")


def _litellm_model_info(model: str) -> Optional[Dict[str, Any]]:
    try:
        import litellm

        return litellm.get_model_info(_normalize_model_id(model))
    except Exception:
        return None


def _matches_any_pattern(model: str, patterns: tuple[str, ...]) -> bool:
    normalized = _normalize_model_id(model).lower()
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
    return False


def resolve_max_input_tokens(model: str) -> int:
    """
    Resolve max input tokens for a model.

    Priority: MAX_TOKENS dict -> LiteLLM model info -> custom_model_max_tokens -> default with warning.
    """
    normalized = _normalize_model_id(model)
    if normalized in MAX_TOKENS:
        return MAX_TOKENS[normalized]
    if model in MAX_TOKENS:
        return MAX_TOKENS[model]

    info = _litellm_model_info(model)
    if info:
        max_input = info.get("max_input_tokens")
        if isinstance(max_input, int) and max_input > 0:
            return max_input

    settings = get_settings()
    custom = getattr(settings.config, "custom_model_max_tokens", -1)
    if custom and custom > 0:
        return custom

    get_logger().warning(
        f"Model {model} is not in MAX_TOKENS and has no LiteLLM mapping; "
        f"using default max input tokens {DEFAULT_MAX_INPUT_TOKENS}. "
        f"Set config.custom_model_max_tokens to override."
    )
    return DEFAULT_MAX_INPUT_TOKENS


def get_model_capabilities(model: str) -> Dict[str, bool]:
    """Return runtime capability flags for a model."""
    normalized = _normalize_model_id(model)
    info = _litellm_model_info(model) or {}

    in_static_reasoning = normalized in SUPPORT_REASONING_EFFORT_MODELS
    in_static_user_only = normalized in USER_MESSAGE_ONLY_MODELS
    in_static_claude_thinking = normalized in CLAUDE_EXTENDED_THINKING_MODELS

    supported_params = info.get("supported_openai_params") or []
    supports_reasoning = bool(info.get("supports_reasoning"))

    if supported_params:
        supports_temperature = "temperature" in supported_params
    elif _matches_any_pattern(model, _NO_TEMPERATURE_PATTERNS):
        supports_temperature = False
    else:
        supports_temperature = True

    supports_reasoning_effort = in_static_reasoning or supports_reasoning or _matches_any_pattern(
        model, _REASONING_PATTERNS
    )

    user_message_only = (
        in_static_user_only
        or _matches_any_pattern(model, _USER_MESSAGE_ONLY_PATTERNS)
    )

    claude_extended_thinking = in_static_claude_thinking or (
        "claude" in normalized.lower()
        and ("sonnet" in normalized.lower() or "opus" in normalized.lower())
        and "haiku" not in normalized.lower()
    )

    return {
        "supports_temperature": supports_temperature,
        "supports_reasoning_effort": supports_reasoning_effort,
        "user_message_only": user_message_only,
        "claude_extended_thinking": claude_extended_thinking,
    }


def model_supports_temperature(model: str) -> bool:
    return get_model_capabilities(model)["supports_temperature"]


def model_supports_reasoning_effort(model: str) -> bool:
    return get_model_capabilities(model)["supports_reasoning_effort"]


def model_is_user_message_only(model: str) -> bool:
    return get_model_capabilities(model)["user_message_only"]


def model_supports_claude_extended_thinking(model: str) -> bool:
    return get_model_capabilities(model)["claude_extended_thinking"]
