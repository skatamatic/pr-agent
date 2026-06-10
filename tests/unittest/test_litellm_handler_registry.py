import pytest

from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler


def _fake_response_dict():
    return {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


class FakeConfig:
    custom_reasoning_model = False
    reasoning_effort = "high"
    seed = -1
    ai_timeout = 60

    def get(self, key, default=None):
        return default


class FakeSettings:
    config = FakeConfig()
    litellm = type("Litellm", (), {"get": lambda self, key, default=False: default})()

    def get(self, key, default=None):
        return default


@pytest.fixture
def handler_settings(monkeypatch):
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.get_settings",
        lambda: FakeSettings(),
    )


@pytest.fixture
def stub_prepare_logs(monkeypatch):
    monkeypatch.setattr(
        LiteLLMAIHandler,
        "prepare_logs",
        lambda self, response, system, user, resp, finish_reason: {},
    )


@pytest.mark.asyncio
async def test_chat_completion_adds_temperature_when_supported(
    monkeypatch, handler_settings, stub_prepare_logs
):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _fake_response_dict()

    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_temperature",
        lambda _model: True,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_reasoning_effort",
        lambda _model: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_is_user_message_only",
        lambda _model: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_claude_extended_thinking",
        lambda _model: False,
    )

    handler = LiteLLMAIHandler()
    await handler.chat_completion(
        model="gpt-4o",
        system="system",
        user="user",
        temperature=0.3,
    )

    assert captured.get("temperature") == 0.3
    assert "reasoning_effort" not in captured


@pytest.mark.asyncio
async def test_chat_completion_adds_reasoning_effort_when_supported(
    monkeypatch, handler_settings, stub_prepare_logs
):
    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _fake_response_dict()

    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.acompletion",
        fake_acompletion,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_temperature",
        lambda _model: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_reasoning_effort",
        lambda _model: True,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_is_user_message_only",
        lambda _model: False,
    )
    monkeypatch.setattr(
        "pr_agent.algo.ai_handlers.litellm_ai_handler.model_supports_claude_extended_thinking",
        lambda _model: False,
    )

    handler = LiteLLMAIHandler()
    await handler.chat_completion(
        model="o3-mini",
        system="system",
        user="user",
        temperature=0.2,
    )

    assert "temperature" not in captured
    assert captured.get("reasoning_effort") == "high"
