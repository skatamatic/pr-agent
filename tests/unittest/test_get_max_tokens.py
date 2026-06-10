import pytest
from pr_agent.algo.utils import get_max_tokens, MAX_TOKENS
import pr_agent.algo.utils as utils

class TestGetMaxTokens:

    # Test if the file is in MAX_TOKENS
    def test_model_max_tokens(self, monkeypatch):
        fake_settings = type('', (), {
            'config': type('', (), {
                'custom_model_max_tokens': 0,
                'max_model_tokens': 0
            })()
        })()

        monkeypatch.setattr(utils, "get_settings", lambda: fake_settings)

        model = "gpt-3.5-turbo"
        expected = MAX_TOKENS[model]

        assert get_max_tokens(model) == expected

    # Test situations where the model is not registered and exists as a custom model
    def test_model_has_custom(self, monkeypatch):
        fake_settings = type('', (), {
            'config': type('', (), {
                'custom_model_max_tokens': 5000,
                'max_model_tokens': 0  # 제한 없음
            })()
        })()

        monkeypatch.setattr(utils, "get_settings", lambda: fake_settings)
        import pr_agent.algo.model_registry as model_registry
        monkeypatch.setattr(model_registry, "get_settings", lambda: fake_settings)
        monkeypatch.setattr(model_registry, "_litellm_model_info", lambda _m: None)

        model = "custom-model"
        expected = 5000

        assert get_max_tokens(model) == expected

    def test_model_not_max_tokens_uses_default(self, monkeypatch):
        fake_settings = type('', (), {
            'config': type('', (), {
                'custom_model_max_tokens': 0,
                'max_model_tokens': 0
            })()
        })()

        monkeypatch.setattr(utils, "get_settings", lambda: fake_settings)
        import pr_agent.algo.model_registry as model_registry
        monkeypatch.setattr(
            "pr_agent.algo.model_registry.resolve_max_input_tokens",
            lambda _m: model_registry.DEFAULT_MAX_INPUT_TOKENS,
        )

        assert get_max_tokens("custom-model") == model_registry.DEFAULT_MAX_INPUT_TOKENS

    def test_litellm_fallback_path(self, monkeypatch):
        fake_settings = type('', (), {
            'config': type('', (), {
                'custom_model_max_tokens': 0,
                'max_model_tokens': 0
            })()
        })()
        monkeypatch.setattr(utils, "get_settings", lambda: fake_settings)
        import pr_agent.algo.model_registry as model_registry
        monkeypatch.setattr(
            "pr_agent.algo.model_registry.resolve_max_input_tokens",
            lambda _m: 200000,
        )

        assert get_max_tokens("brand-new-model") == 200000

    def test_model_max_tokens_with__limit(self, monkeypatch):
        fake_settings = type('', (), {
            'config': type('', (), {
                'custom_model_max_tokens': 0,
                'max_model_tokens': 10000
            })()
        })()

        monkeypatch.setattr(utils, "get_settings", lambda: fake_settings)

        model = "gpt-3.5-turbo"  # this model setting is 160000
        expected = 10000

        assert get_max_tokens(model) == expected
