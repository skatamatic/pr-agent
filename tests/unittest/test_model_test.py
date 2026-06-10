import pytest
from contextlib import contextmanager

from pr_agent.algo.model_test import (
    BENCHMARK_USER_PROMPT,
    ModelTestResult,
    run_model_benchmark,
)


class TestRunModelBenchmark:
    def test_prompt_is_substantive(self):
        assert len(BENCHMARK_USER_PROMPT) >= 800

    @pytest.mark.asyncio
    async def test_success_metrics(self, monkeypatch):
        async def fake_chat_completion(self, model, system, user, temperature=0.2, img_path=None):
            return '{"summary":"ok"}', "stop", {"input_tokens": 900, "output_tokens": 120}

        monkeypatch.setattr(
            "pr_agent.algo.model_test.LiteLLMAIHandler.chat_completion",
            fake_chat_completion,
        )

        result = await run_model_benchmark("gpt-4o")
        assert isinstance(result, ModelTestResult)
        assert result.success is True
        assert result.input_tokens == 900
        assert result.output_tokens == 120
        assert result.latency_ms >= 0
        assert result.output_tokens_per_sec > 0
        assert result.total_tokens_per_sec > 0

    @pytest.mark.asyncio
    async def test_missing_usage_still_succeeds(self, monkeypatch):
        async def fake_chat_completion(self, model, system, user, temperature=0.2, img_path=None):
            return "ok", "stop", None

        monkeypatch.setattr(
            "pr_agent.algo.model_test.LiteLLMAIHandler.chat_completion",
            fake_chat_completion,
        )

        result = await run_model_benchmark("gpt-4o")
        assert result.success is True
        assert result.input_tokens == 0
        assert result.output_tokens == 0

    @pytest.mark.asyncio
    async def test_provider_failure(self, monkeypatch):
        async def fake_chat_completion(self, model, system, user, temperature=0.2, img_path=None):
            raise RuntimeError("rate limited")

        monkeypatch.setattr(
            "pr_agent.algo.model_test.LiteLLMAIHandler.chat_completion",
            fake_chat_completion,
        )

        result = await run_model_benchmark("gpt-4o")
        assert result.success is False
        assert "rate limited" in (result.error or "")

    @pytest.mark.asyncio
    async def test_benchmark_applies_secrets(self, monkeypatch):
        captured = {}

        @contextmanager
        def fake_temp_credentials(secrets):
            captured["secrets"] = secrets
            yield

        async def fake_chat_completion(self, model, system, user, temperature=0.2, img_path=None):
            return "ok", "stop", {"input_tokens": 1, "output_tokens": 1}

        monkeypatch.setattr(
            "pr_agent.algo.model_test.temporary_litellm_credentials",
            fake_temp_credentials,
        )
        monkeypatch.setattr(
            "pr_agent.algo.model_test.LiteLLMAIHandler.chat_completion",
            fake_chat_completion,
        )

        secrets = {"openai": {"key": "sk-test"}}
        await run_model_benchmark("gpt-4o", secrets=secrets)
        assert captured["secrets"] == secrets

    @pytest.mark.asyncio
    async def test_missing_model(self):
        result = await run_model_benchmark("")
        assert result.success is False
        assert result.error == "Model is required"
