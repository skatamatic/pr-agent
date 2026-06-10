import pytest

from pr_agent.algo.model_discovery import (
    DiscoveredModel,
    DiscoveryResult,
    _merge_models,
    discover_models_async,
    is_specialty_model,
)


class TestIsSpecialtyModel:
    @pytest.mark.parametrize(
        "model_id",
        [
            "text-embedding-ada-002",
            "whisper-1",
            "dall-e-3",
            "gemini/text-embedding-004",
        ],
    )
    def test_excludes_specialty_models(self, model_id):
        assert is_specialty_model(model_id) is True

    @pytest.mark.parametrize(
        "model_id",
        [
            "gpt-4o",
            "anthropic/claude-sonnet-4-6-20260205",
            "gemini/gemini-2.0-flash",
        ],
    )
    def test_includes_chat_models(self, model_id):
        assert is_specialty_model(model_id) is False


class TestMergeModels:
    def test_live_models_ranked_before_litellm(self):
        live = [
            DiscoveredModel(
                id="gpt-5",
                display_name="gpt-5",
                provider="openai",
                source="live",
            )
        ]
        fallback = [
            DiscoveredModel(
                id="gpt-5",
                display_name="gpt-5",
                provider="openai",
                source="litellm",
            ),
            DiscoveredModel(
                id="gpt-4o",
                display_name="gpt-4o",
                provider="openai",
                source="litellm",
            ),
        ]
        result = _merge_models(live, fallback)
        assert result.all_ids[0] == "gpt-5"
        assert "gpt-4o" in result.all_ids
        assert result.providers["OpenAI"][0]["source"] == "live"

    def test_dedupes_by_id(self):
        live = [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="live"),
        ]
        fallback = [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
        ]
        result = _merge_models(live, fallback)
        assert result.all_ids.count("gpt-4o") == 1


@pytest.mark.asyncio
async def test_discover_models_openai_live_and_litellm_fallback(monkeypatch):
    async def fake_openai(_key):
        return [
            DiscoveredModel(id="gpt-5", display_name="gpt-5", provider="openai", source="live"),
        ]

    monkeypatch.setattr("pr_agent.algo.model_discovery._fetch_openai_models", fake_openai)
    monkeypatch.setattr(
        "pr_agent.algo.model_discovery._litellm_chat_models",
        lambda: [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
        ],
    )

    result = await discover_models_async(
        secrets={"openai": {"key": "sk-test"}},
        include_litellm_fallback=True,
    )
    assert isinstance(result, DiscoveryResult)
    assert "gpt-5" in result.all_ids
    assert "gpt-4o" in result.all_ids
    assert result.provider_status["openai"] == "configured"


@pytest.mark.asyncio
async def test_discover_models_provider_error_does_not_fail_whole_response(monkeypatch):
    async def failing_openai(_key):
        raise RuntimeError("network down")

    monkeypatch.setattr("pr_agent.algo.model_discovery._fetch_openai_models", failing_openai)
    monkeypatch.setattr(
        "pr_agent.algo.model_discovery._litellm_chat_models",
        lambda: [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
        ],
    )

    result = await discover_models_async(
        secrets={"openai": {"key": "sk-test"}},
        include_litellm_fallback=True,
    )
    assert result.provider_errors.get("openai") == "network down"
    assert "gpt-4o" in result.all_ids


@pytest.mark.asyncio
async def test_discover_models_no_key_skips_live(monkeypatch):
    monkeypatch.setattr(
        "pr_agent.algo.model_discovery._litellm_chat_models",
        lambda: [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
        ],
    )
    result = await discover_models_async(secrets={}, include_litellm_fallback=True)
    assert result.provider_status["openai"] == "no_key"
    assert "gpt-4o" in result.all_ids


def test_litellm_chat_models_uses_cache(monkeypatch):
    from pr_agent.algo.model_discovery import _litellm_chat_models, reset_litellm_chat_cache_for_tests

    reset_litellm_chat_cache_for_tests()
    calls = {"count": 0}

    class FakeLitellm:
        model_list = ["gpt-4o"]

        @staticmethod
        def get_model_info(model_id):
            calls["count"] += 1
            return {"mode": "chat", "max_input_tokens": 8000}

    monkeypatch.setitem(__import__("sys").modules, "litellm", FakeLitellm)

    first = _litellm_chat_models()
    second = _litellm_chat_models()
    assert len(first) == 1
    assert first[0].id == "gpt-4o"
    assert calls["count"] == 1
    assert second[0].id == "gpt-4o"
