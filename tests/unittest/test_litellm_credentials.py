"""Tests for litellm_credentials."""

import os

import litellm
import pytest

from pr_agent.algo.litellm_credentials import (
    apply_litellm_credentials_from_secrets,
    temporary_litellm_credentials,
)


class TestApplyLitellmCredentialsFromSecrets:
    def test_openai_key_sets_env_and_module(self):
        apply_litellm_credentials_from_secrets({"openai": {"key": "sk-test-openai"}})
        assert litellm.openai_key == "sk-test-openai"
        assert os.environ.get("OPENAI_API_KEY") == "sk-test-openai"

    def test_anthropic_key(self):
        apply_litellm_credentials_from_secrets({"anthropic": {"key": "sk-ant-test"}})
        assert litellm.anthropic_key == "sk-ant-test"
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test"

    def test_azure_openai_section(self):
        apply_litellm_credentials_from_secrets({
            "openai": {
                "key": "azure-key",
                "api_type": "azure",
                "api_base": "https://example.openai.azure.com",
                "api_version": "2024-06-01",
            }
        })
        assert litellm.azure_key == "azure-key"
        assert litellm.api_base == "https://example.openai.azure.com"
        assert os.environ.get("AZURE_API_BASE") == "https://example.openai.azure.com"
        assert os.environ.get("AZURE_API_VERSION") == "2024-06-01"


class TestTemporaryLitellmCredentials:
    def test_restores_state_after_context(self):
        original_openai = getattr(litellm, "openai_key", None)
        original_env = os.environ.get("OPENAI_API_KEY")

        with temporary_litellm_credentials({"openai": {"key": "sk-temp"}}):
            assert litellm.openai_key == "sk-temp"
            assert os.environ.get("OPENAI_API_KEY") == "sk-temp"

        assert getattr(litellm, "openai_key", None) == original_openai
        if original_env is None:
            assert "OPENAI_API_KEY" not in os.environ
        else:
            assert os.environ.get("OPENAI_API_KEY") == original_env
