"""
Unit tests for config.internal_log_ingest_headers — server-side POST /logs/* auth.

Ensures same-process HTTP self-logging includes Bearer DASHBOARD_API_KEY when configured.
"""
import pytest

import config as dashboard_config
from config import internal_log_ingest_headers


class TestInternalLogIngestHeaders:
    """Pure unit tests for header dict construction."""

    def test_empty_when_api_key_missing(self, monkeypatch):
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", "", raising=False)
        assert internal_log_ingest_headers() == {}

    def test_empty_when_api_key_none(self, monkeypatch):
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", None, raising=False)
        assert internal_log_ingest_headers() == {}

    def test_empty_when_api_key_whitespace_only(self, monkeypatch):
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", "   \t  ", raising=False)
        assert internal_log_ingest_headers() == {}

    def test_bearer_when_api_key_set(self, monkeypatch):
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", "secret-key-123", raising=False)
        h = internal_log_ingest_headers()
        assert h == {"Authorization": "Bearer secret-key-123"}

    def test_strips_leading_trailing_whitespace(self, monkeypatch):
        monkeypatch.setattr(
            dashboard_config.settings,
            "dashboard_api_key",
            "  my-key  ",
            raising=False,
        )
        assert internal_log_ingest_headers() == {"Authorization": "Bearer my-key"}

    def test_coerces_non_string_to_str(self, monkeypatch):
        """Dynaconf / env edge cases: value might not be str."""
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", 99901, raising=False)
        assert internal_log_ingest_headers() == {"Authorization": "Bearer 99901"}

    def test_returns_fresh_dict_each_call(self, monkeypatch):
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", "k", raising=False)
        a = internal_log_ingest_headers()
        b = internal_log_ingest_headers()
        assert a == b
        assert a is not b
        a["Authorization"] = "mutated"
        assert internal_log_ingest_headers() == {"Authorization": "Bearer k"}


class TestInternalLogIngestHeadersIntegration:
    """App accepts the same headers internal callers use."""

    def test_post_logs_immediate_succeeds_with_matching_internal_headers(self, client_app, monkeypatch):
        key = "integration-internal-log-key"
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", key, raising=False)
        payload = {
            "level": "INFO",
            "message": "internal ingest integration",
            "source": "test_internal_log_ingest",
        }
        response = client_app.post(
            "/logs/immediate",
            json=payload,
            headers=internal_log_ingest_headers(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "received"
        assert body.get("id") is not None

    def test_post_logs_immediate_fails_without_auth_when_api_key_required(self, client_app, monkeypatch):
        """When key is set, anonymous request must not succeed."""
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", "required-key", raising=False)
        response = client_app.post(
            "/logs/immediate",
            json={"level": "INFO", "message": "anon", "source": "test"},
        )
        assert response.status_code == 401

    def test_post_logs_batch_succeeds_with_internal_headers(self, client_app, monkeypatch):
        key = "batch-internal-key"
        monkeypatch.setattr(dashboard_config.settings, "dashboard_api_key", key, raising=False)
        response = client_app.post(
            "/logs/batch",
            json={"logs": [{"level": "INFO", "message": "b1", "source": "t"}]},
            headers=internal_log_ingest_headers(),
        )
        assert response.status_code == 200
        assert response.json().get("status") == "received"
        assert response.json().get("count") == 1
