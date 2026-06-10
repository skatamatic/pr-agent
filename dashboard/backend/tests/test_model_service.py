"""Tests for ModelService."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from pr_agent.algo.model_discovery import DiscoveryResult
from services.config_backend import CONFIG_KEY, SECRETS_KEY
from services.model_service import ModelService


@pytest.fixture
def mock_config_service():
    service = MagicMock()
    service._load_toml_from_backend = MagicMock(return_value={})
    return service


@pytest.fixture
def model_service(mock_config_service):
    return ModelService(mock_config_service)


class TestModelServiceDiscoverModels:
    @pytest.mark.asyncio
    async def test_discover_models_returns_grouped_shape(self, model_service, monkeypatch):
        discovery = DiscoveryResult(
            providers={"OpenAI": [{"id": "gpt-4o", "source": "live"}]},
            all_ids=["gpt-4o"],
            provider_errors={},
            provider_status={"openai": "configured"},
        )

        async def fake_discover(**kwargs):
            return discovery

        monkeypatch.setattr("services.model_service.discover_models_async", fake_discover)
        result = await model_service.discover_models()
        assert result["all_ids"] == ["gpt-4o"]
        assert "fetched_at" in result
        assert result["providers"]["OpenAI"][0]["id"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_discover_models_cache_hit(self, model_service, monkeypatch):
        calls = {"count": 0}

        async def fake_discover(**kwargs):
            calls["count"] += 1
            return DiscoveryResult(all_ids=["gpt-4o"])

        monkeypatch.setattr("services.model_service.discover_models_async", fake_discover)
        await model_service.discover_models()
        await model_service.discover_models()
        assert calls["count"] == 1

    @pytest.mark.asyncio
    async def test_discover_models_force_refresh_bypasses_cache(self, model_service, monkeypatch):
        calls = {"count": 0}

        async def fake_discover(**kwargs):
            calls["count"] += 1
            return DiscoveryResult(all_ids=["gpt-4o"])

        monkeypatch.setattr("services.model_service.discover_models_async", fake_discover)
        await model_service.discover_models()
        await model_service.discover_models(force_refresh=True)
        assert calls["count"] == 2


class TestModelServiceTestModel:
    @pytest.mark.asyncio
    async def test_test_model_success(self, model_service, monkeypatch):
        async def fake_benchmark(model, temperature=0.2, secrets=None):
            from pr_agent.algo.model_test import ModelTestResult

            return ModelTestResult(
                success=True,
                model=model,
                latency_ms=1000,
                input_tokens=900,
                output_tokens=100,
                output_tokens_per_sec=100.0,
                total_tokens_per_sec=1000.0,
                finish_reason="stop",
            )

        monkeypatch.setattr("services.model_service.run_model_benchmark", fake_benchmark)
        result = await model_service.test_model("gpt-4o")
        assert result["success"] is True
        assert result["output_tokens_per_sec"] == 100.0

    @pytest.mark.asyncio
    async def test_test_model_missing_model(self, model_service):
        result = await model_service.test_model("")
        assert result["success"] is False
        assert result["error"] == "Model is required"

    @pytest.mark.asyncio
    async def test_test_model_applies_payload_keys(self, model_service, monkeypatch):
        captured = {}

        async def fake_benchmark(model, temperature=0.2, secrets=None):
            captured["secrets"] = secrets
            from pr_agent.algo.model_test import ModelTestResult

            return ModelTestResult(success=True, model=model)

        monkeypatch.setattr("services.model_service.run_model_benchmark", fake_benchmark)
        await model_service.test_model(
            "gpt-4o",
            api_keys={"openai": "sk-test-key"},
            use_saved_config=False,
        )
        assert captured["secrets"]["openai"]["key"] == "sk-test-key"

    def test_build_openai_config_merges_secrets_azure(self, model_service, mock_config_service):
        mock_config_service._load_toml_from_backend.side_effect = lambda key: {
            CONFIG_KEY: {},
            SECRETS_KEY: {
                "openai": {
                    "key": "azure-key",
                    "api_type": "azure",
                    "api_base": "https://example.openai.azure.com",
                    "api_version": "2024-06-01",
                }
            },
        }.get(key, {})
        openai_config = model_service._build_openai_config()
        assert openai_config["api_type"] == "azure"
        assert openai_config["api_base"] == "https://example.openai.azure.com"
        assert openai_config["api_version"] == "2024-06-01"

    def test_build_secrets_ignores_masked_keys(self, model_service, mock_config_service):
        mock_config_service._load_toml_from_backend.return_value = {
            "openai": {"key": "saved-key"},
        }
        secrets = model_service._build_secrets_dict(api_keys_override={"openai": "***"})
        assert secrets["openai"]["key"] == "saved-key"

    @pytest.mark.asyncio
    async def test_discover_models_cache_expires(self, model_service, monkeypatch):
        calls = {"count": 0}

        async def fake_discover(**kwargs):
            calls["count"] += 1
            return DiscoveryResult(all_ids=[f"model-{calls['count']}"])

        monkeypatch.setattr("services.model_service.discover_models_async", fake_discover)
        model_service.CACHE_TTL_SECONDS = 0
        first = await model_service.discover_models()
        second = await model_service.discover_models()
        assert first["all_ids"] == ["model-1"]
        assert second["all_ids"] == ["model-2"]
        assert calls["count"] == 2

    def test_clear_cache(self, model_service):
        model_service._cache["key"] = {"stored_at": 0, "payload": {"all_ids": ["old"]}}
        model_service.clear_cache()
        assert model_service._cache == {}
