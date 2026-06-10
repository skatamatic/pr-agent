import pytest

from pr_agent.algo import MAX_TOKENS
from pr_agent.algo.model_registry import (
    DEFAULT_MAX_INPUT_TOKENS,
    get_model_capabilities,
    model_supports_temperature,
    resolve_max_input_tokens,
)
import pr_agent.algo.model_registry as model_registry


class TestResolveMaxInputTokens:
    def test_max_tokens_dict_takes_priority(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: {"max_input_tokens": 999})
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_model_max_tokens": 5000})()})(),
        )
        assert resolve_max_input_tokens("gpt-3.5-turbo") == MAX_TOKENS["gpt-3.5-turbo"]

    def test_litellm_info_fallback(self, monkeypatch):
        monkeypatch.setattr(
            model_registry,
            "_litellm_model_info",
            lambda _m: {"max_input_tokens": 200000},
        )
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_model_max_tokens": 0})()})(),
        )
        assert resolve_max_input_tokens("brand-new-model") == 200000

    def test_custom_model_max_tokens_fallback(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_model_max_tokens": 64000})()})(),
        )
        assert resolve_max_input_tokens("brand-new-model") == 64000

    def test_max_tokens_dict_normalizes_azure_prefix(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_model_max_tokens": -1})()})(),
        )
        assert resolve_max_input_tokens("azure/gpt-4o") == MAX_TOKENS["gpt-4o"]

    def test_default_with_warning(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_model_max_tokens": -1})()})(),
        )
        assert resolve_max_input_tokens("totally-unknown-model") == DEFAULT_MAX_INPUT_TOKENS


class TestGetModelCapabilities:
    def test_o1_no_temperature(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_reasoning_model": False})()})(),
        )
        caps = get_model_capabilities("o1-mini")
        assert caps["supports_temperature"] is False
        assert caps["user_message_only"] is True

    def test_gpt5_reasoning_from_litellm(self, monkeypatch):
        monkeypatch.setattr(
            model_registry,
            "_litellm_model_info",
            lambda _m: {
                "supports_reasoning": True,
                "supported_openai_params": ["temperature", "max_tokens"],
            },
        )
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_reasoning_model": False})()})(),
        )
        caps = get_model_capabilities("custom-gpt-5-model")
        assert caps["supports_temperature"] is True
        assert caps["supports_reasoning_effort"] is True

    def test_gpt4o_supports_temperature_without_litellm_info(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)
        caps = get_model_capabilities("gpt-4o")
        assert caps["supports_temperature"] is True

    def test_claude_extended_thinking_heuristic(self, monkeypatch):
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_reasoning_model": False})()})(),
        )
        caps = get_model_capabilities("anthropic/claude-sonnet-4-6-20260205")
        assert caps["claude_extended_thinking"] is True

    def test_model_supports_temperature_helper(self, monkeypatch):
        monkeypatch.setattr(
            model_registry,
            "_litellm_model_info",
            lambda _m: {"supported_openai_params": ["temperature"]},
        )
        monkeypatch.setattr(
            model_registry,
            "get_settings",
            lambda: type("", (), {"config": type("", (), {"custom_reasoning_model": False})()})(),
        )
        assert model_supports_temperature("custom-chat-model") is True
