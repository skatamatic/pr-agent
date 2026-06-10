import pytest

from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.litellm_credentials import temporary_litellm_credentials


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
