import pytest

import pr_agent.algo.ai_handlers.litellm_ai_handler as handler_mod
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.litellm_credentials import temporary_litellm_credentials
from pr_agent.algo.model_registry import (
    REASONING_STYLE_ANTHROPIC_ADAPTIVE,
    REASONING_STYLE_ANTHROPIC_BUDGET,
    REASONING_STYLE_OPENAI,
)


def _fake_settings_with_openai_key():
    return type(
        "Settings",
        (),
        {
            "get": lambda self, key, default=None: "saved-key" if key == "OPENAI.KEY" else default,
            "openai": type("", (), {"key": "saved-key", "api_type": "", "api_version": "", "api_base": "", "org": ""})(),
            "config": type("", (), {"model": "gpt-4o"})(),
            "litellm": type("", (), {"drop_params": None})(),
            "aws": type("", (), {})(),
        },
    )()


def test_handler_preserves_injected_openai_key(monkeypatch):
    """LiteLLMAIHandler(use_injected_credentials=True) must not overwrite temporary keys."""
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings",
        _fake_settings_with_openai_key,
    )

    import litellm

    with temporary_litellm_credentials({"openai": {"key": "sk-override-key"}}):
        LiteLLMAIHandler(use_injected_credentials=True)
        assert litellm.openai_key == "sk-override-key"


def test_handler_applies_settings_when_not_injected(monkeypatch):
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings",
        _fake_settings_with_openai_key,
    )

    import litellm

    handler = LiteLLMAIHandler(use_injected_credentials=False)
    assert litellm.openai_key == "saved-key"
    assert handler.azure is False


@pytest.mark.asyncio
async def test_chat_completion_no_azure_double_prefix(monkeypatch):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured["model"] = kwargs.get("model")
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    class FakeConfig:
        custom_reasoning_model = False
        reasoning_effort = "medium"
        seed = -1
        ai_timeout = 60

        def get(self, key, default=None):
            return default

    class FakeSettings:
        config = FakeConfig()
        litellm = type("Litellm", (), {"get": lambda self, key, default=False: default})()

        def get(self, key, default=None):
            return default

    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings",
        lambda: FakeSettings(),
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(
        LiteLLMAIHandler,
        "prepare_logs",
        lambda self, *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_temperature",
        lambda _m: True,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_reasoning_effort",
        lambda _m: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_is_user_message_only",
        lambda _m: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_claude_extended_thinking",
        lambda _m: False,
    )

    handler = LiteLLMAIHandler()
    handler.azure = True
    await handler.chat_completion(model="azure/my-deploy", system="s", user="u")

    assert captured["model"] == "azure/my-deploy"


@pytest.mark.asyncio
async def test_chat_completion_drops_unsupported_temperature(monkeypatch):
    """A provider rejecting `temperature` should cause a retry without it, not a hard failure."""
    import litellm

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(dict(kwargs))
        if "temperature" in kwargs:
            raise litellm.BadRequestError(
                message="AnthropicException - `temperature` is deprecated for this model.",
                model=kwargs.get("model"),
                llm_provider="anthropic",
            )
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    class FakeConfig:
        custom_reasoning_model = False
        reasoning_effort = "medium"
        seed = -1
        ai_timeout = 60

        def get(self, key, default=None):
            return default

    class FakeSettings:
        config = FakeConfig()
        litellm = type("Litellm", (), {"get": lambda self, key, default=False: default})()

        def get(self, key, default=None):
            return default

    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings",
        lambda: FakeSettings(),
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(LiteLLMAIHandler, "prepare_logs", lambda self, *args, **kwargs: {})
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_temperature",
        lambda _m: True,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_reasoning_effort",
        lambda _m: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_is_user_message_only",
        lambda _m: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_claude_extended_thinking",
        lambda _m: False,
    )

    handler = LiteLLMAIHandler()
    resp, finish_reason, usage = await handler.chat_completion(
        model="anthropic/claude-opus-4-8", system="s", user="u"
    )

    assert resp == "ok"
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_apply_reasoning_level_anthropic_adaptive(monkeypatch):
    monkeypatch.setattr(handler_mod, "model_reasoning_style", lambda _m: REASONING_STYLE_ANTHROPIC_ADAPTIVE)
    handler = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    kwargs = {"model": "anthropic/claude-opus-4-8", "temperature": 0.2, "max_tokens": 1000}
    out = handler._apply_reasoning_level("anthropic/claude-opus-4-8", "anthropic/claude-opus-4-8", "high", kwargs)
    assert out["thinking"] == {"type": "adaptive"}
    assert out["output_config"] == {"effort": "high"}
    # Adaptive-thinking models deprecate temperature; it must be removed.
    assert "temperature" not in out


def test_apply_reasoning_level_anthropic_budget(monkeypatch):
    monkeypatch.setattr(handler_mod, "model_reasoning_style", lambda _m: REASONING_STYLE_ANTHROPIC_BUDGET)
    handler = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    kwargs = {"model": "anthropic/claude-3-7-sonnet", "temperature": 0.2, "max_tokens": 1000}
    out = handler._apply_reasoning_level("m", "m", "high", kwargs)
    assert out["thinking"]["type"] == "enabled"
    assert out["thinking"]["budget_tokens"] > 0
    assert out["max_tokens"] > out["thinking"]["budget_tokens"]
    assert out["temperature"] == 1


def test_apply_reasoning_level_openai(monkeypatch):
    monkeypatch.setattr(handler_mod, "model_reasoning_style", lambda _m: REASONING_STYLE_OPENAI)
    handler = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    kwargs = {"model": "gpt-5", "temperature": 0.2}
    out = handler._apply_reasoning_level("gpt-5", "gpt-5", "high", kwargs)
    assert out["reasoning_effort"] == "high"
    assert "thinking" not in out


def test_negotiate_switches_enabled_to_adaptive():
    handler = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    kwargs = {
        "thinking": {"type": "enabled", "budget_tokens": 2048},
        "output_config": {"effort": "medium"},
        "temperature": 1,
        "max_tokens": 6000,
    }
    msg = (
        '"thinking.type.enabled" is not supported for this model. '
        'use "thinking.type.adaptive" and "output_config.effort"'
    )
    repair = handler._negotiate_thinking_params(kwargs, msg, set())
    assert repair
    assert kwargs["thinking"] == {"type": "adaptive"}
    assert kwargs["output_config"] == {"effort": "medium"}
    assert "temperature" not in kwargs


def test_negotiate_switches_adaptive_to_budget():
    handler = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    kwargs = {"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}, "max_tokens": 100}
    repair = handler._negotiate_thinking_params(kwargs, "adaptive thinking is not supported on this model", set())
    assert repair
    assert kwargs["thinking"]["type"] == "enabled"
    assert "output_config" not in kwargs
    assert kwargs["max_tokens"] > kwargs["thinking"]["budget_tokens"]
    assert kwargs["temperature"] == 1


@pytest.mark.asyncio
async def test_fallback_negotiates_thinking_style(monkeypatch):
    import litellm

    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(dict(kwargs))
        th = kwargs.get("thinking")
        if isinstance(th, dict) and th.get("type") == "enabled":
            raise litellm.BadRequestError(
                message=('AnthropicException - "thinking.type.enabled" is not supported for this model. '
                         'Use "thinking.type.adaptive" and "output_config.effort"'),
                model=kwargs.get("model"),
                llm_provider="anthropic",
            )
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    monkeypatch.setattr(handler_mod, "acompletion", fake_acompletion)
    handler = LiteLLMAIHandler.__new__(LiteLLMAIHandler)
    resp = await handler._acompletion_with_param_fallback(
        {
            "model": "anthropic/claude-opus-4-8",
            "thinking": {"type": "enabled", "budget_tokens": 2048},
            "temperature": 1,
            "max_tokens": 6000,
        }
    )
    assert resp["choices"][0]["message"]["content"] == "ok"
    assert len(calls) == 2
    assert calls[1]["thinking"] == {"type": "adaptive"}
