import pytest

from pr_agent.algo.model_discovery import (
    DiscoveredModel,
    DiscoveryResult,
    _fetch_anthropic_models,
    _filter_models_for_providers,
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
            "anthropic/claude-haiku-4-5-20251001",
            "claude-3-5-haiku-20241022",
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


class TestFilterModelsForProviders:
    def test_keeps_only_configured_providers(self):
        models = [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
            DiscoveredModel(
                id="anthropic/claude-haiku-4-5-20251001",
                display_name="haiku",
                provider="anthropic",
                source="litellm",
            ),
        ]
        filtered = _filter_models_for_providers(models, {"anthropic"})
        assert len(filtered) == 1
        assert filtered[0].provider == "anthropic"


@pytest.mark.asyncio
async def test_discover_models_no_key_returns_empty_catalog(monkeypatch):
    monkeypatch.setattr(
        "pr_agent.algo.model_discovery._litellm_chat_models",
        lambda: [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
        ],
    )
    result = await discover_models_async(secrets={}, include_litellm_fallback=True)
    assert result.provider_status["openai"] == "no_key"
    assert result.all_ids == []
    assert result.providers == {}


@pytest.mark.asyncio
async def test_discover_models_anthropic_only_excludes_openai_litellm(monkeypatch):
    async def fake_anthropic(_key):
        return [
            DiscoveredModel(
                id="anthropic/claude-sonnet-4-6-20260205",
                display_name="Sonnet",
                provider="anthropic",
                source="live",
            ),
        ]

    monkeypatch.setattr("pr_agent.algo.model_discovery._fetch_anthropic_models", fake_anthropic)
    monkeypatch.setattr(
        "pr_agent.algo.model_discovery._litellm_chat_models",
        lambda: [
            DiscoveredModel(id="gpt-4o", display_name="gpt-4o", provider="openai", source="litellm"),
            DiscoveredModel(
                id="anthropic/claude-haiku-4-5-20251001",
                display_name="Haiku",
                provider="anthropic",
                source="litellm",
            ),
        ],
    )

    result = await discover_models_async(
        secrets={"anthropic": {"key": "sk-ant-test"}},
        include_litellm_fallback=True,
    )
    assert "gpt-4o" not in result.all_ids
    assert "anthropic/claude-haiku-4-5-20251001" in result.all_ids
    assert "Anthropic" in result.providers
    assert "OpenAI" not in result.providers


@pytest.mark.asyncio
async def test_fetch_anthropic_models_paginates(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params=None, headers=None):
            calls["count"] += 1
            if params.get("after_id"):
                return FakeResponse(
                    {
                        "data": [
                            {
                                "id": "claude-haiku-4-5-20251001",
                                "display_name": "Claude Haiku 4.5",
                                "max_input_tokens": 200000,
                            }
                        ],
                        "has_more": False,
                    }
                )
            return FakeResponse(
                {
                    "data": [
                        {
                            "id": "claude-opus-4-6-20260205",
                            "display_name": "Claude Opus 4.6",
                        }
                    ],
                    "has_more": True,
                    "last_id": "claude-opus-4-6-20260205",
                }
            )

    monkeypatch.setattr("pr_agent.algo.model_discovery.httpx.AsyncClient", lambda timeout=15.0: FakeClient())

    models = await _fetch_anthropic_models("sk-ant-test")
    assert calls["count"] == 2
    ids = {model.id for model in models}
    assert "anthropic/claude-haiku-4-5-20251001" in ids
    assert "anthropic/claude-opus-4-6-20260205" in ids


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
