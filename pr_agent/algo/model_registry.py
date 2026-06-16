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
    r"^gpt-5",
    r"deepseek/deepseek-reasoner",
    r"deepseek-reasoner",
    r"reasoner",
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
# Anthropic models that use the newer "adaptive" thinking API. These deprecated the
# `temperature` parameter and reject LiteLLM's reasoning_effort -> thinking.enabled
# translation (they require thinking.type=adaptive + output_config.effort).
_ANTHROPIC_ADAPTIVE_THINKING_PATTERNS = (
    r"claude-opus-4-8",
    r"claude-sonnet-4-8",
    r"claude-haiku-4-8",
)

# Reasoning styles used by the abstraction layer to decide how to express "reasoning level".
REASONING_STYLE_OPENAI = "openai"  # OpenAI-style `reasoning_effort` param
REASONING_STYLE_ANTHROPIC_ADAPTIVE = "anthropic_adaptive"  # thinking.type=adaptive + output_config.effort
REASONING_STYLE_ANTHROPIC_BUDGET = "anthropic_budget"  # thinking.type=enabled + budget_tokens


def _is_anthropic_model(model: str) -> bool:
    normalized = _normalize_model_id(model).lower()
    return model.lower().startswith("anthropic/") or "claude" in normalized


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

    is_anthropic = _is_anthropic_model(model)
    is_anthropic_adaptive = is_anthropic and _matches_any_pattern(
        model, _ANTHROPIC_ADAPTIVE_THINKING_PATTERNS
    )

    claude_extended_thinking = in_static_claude_thinking or (
        "claude" in normalized.lower()
        and ("sonnet" in normalized.lower() or "opus" in normalized.lower())
        and "haiku" not in normalized.lower()
    )

    # Decide how the model expresses "reasoning level".
    # Anthropic models reason via their native `thinking` API rather than the OpenAI
    # `reasoning_effort` parameter, so we translate the level in the abstraction layer.
    if is_anthropic:
        if is_anthropic_adaptive:
            reasoning_style = REASONING_STYLE_ANTHROPIC_ADAPTIVE
        elif claude_extended_thinking:
            reasoning_style = REASONING_STYLE_ANTHROPIC_BUDGET
        else:
            reasoning_style = None
    elif in_static_reasoning or supports_reasoning or _matches_any_pattern(model, _REASONING_PATTERNS):
        reasoning_style = REASONING_STYLE_OPENAI
    else:
        reasoning_style = None

    supports_reasoning_effort = reasoning_style is not None

    # Temperature support.
    if is_anthropic_adaptive:
        # Newer Anthropic "adaptive thinking" models deprecated `temperature` entirely.
        supports_temperature = False
    elif supported_params:
        supports_temperature = "temperature" in supported_params
    elif _matches_any_pattern(model, _NO_TEMPERATURE_PATTERNS):
        supports_temperature = False
    elif reasoning_style == REASONING_STYLE_OPENAI:
        # OpenAI reasoning models (o-series, gpt-5, deepseek-reasoner, etc.) reject a custom
        # temperature. When we have no explicit param metadata, err on the safe side.
        supports_temperature = False
    else:
        supports_temperature = True

    user_message_only = (
        in_static_user_only
        or _matches_any_pattern(model, _USER_MESSAGE_ONLY_PATTERNS)
    )

    return {
        "supports_temperature": supports_temperature,
        "supports_reasoning_effort": supports_reasoning_effort,
        "user_message_only": user_message_only,
        "claude_extended_thinking": claude_extended_thinking,
        "reasoning_style": reasoning_style,
    }


def model_supports_temperature(model: str) -> bool:
    return get_model_capabilities(model)["supports_temperature"]


def model_supports_reasoning_effort(model: str) -> bool:
    return get_model_capabilities(model)["supports_reasoning_effort"]


def model_is_user_message_only(model: str) -> bool:
    return get_model_capabilities(model)["user_message_only"]


def model_supports_claude_extended_thinking(model: str) -> bool:
    return get_model_capabilities(model)["claude_extended_thinking"]


def model_reasoning_style(model: str) -> Optional[str]:
    """Return how the model expresses reasoning level (see REASONING_STYLE_* constants)."""
    return get_model_capabilities(model)["reasoning_style"]
