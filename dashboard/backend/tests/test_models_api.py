"""API tests for model discovery and benchmark endpoints."""

from unittest.mock import AsyncMock

import pytest


class TestModelsAPI:
    def test_get_available_models_requires_auth(self, client_app):
        response = client_app.get("/api/models/available")
        assert response.status_code == 401

    def test_get_available_models_success(self, client_app, auth_headers, monkeypatch):
        async def fake_discover(force_refresh=False):
            return {
                "providers": {"OpenAI": [{"id": "gpt-4o", "source": "live"}]},
                "all_ids": ["gpt-4o"],
                "provider_errors": {},
                "provider_status": {"openai": "configured"},
                "fetched_at": "2026-01-01T00:00:00+00:00",
            }

        from main import app

        dashboard_app = app.router.routes  # noqa: F841 - ensure import works
        import main as backend_main

        backend_main.dashboard_app.model_service.discover_models = AsyncMock(side_effect=fake_discover)

        response = client_app.get("/api/models/available", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        data = body.get("data") or body
        assert "gpt-4o" in data["all_ids"]

    def test_post_model_test_requires_auth(self, client_app):
        response = client_app.post("/api/models/test", json={"model": "gpt-4o"})
        assert response.status_code == 401

    def test_post_model_test_missing_model(self, client_app, auth_headers):
        response = client_app.post("/api/models/test", json={}, headers=auth_headers)
        assert response.status_code == 400

    def test_post_model_test_success(self, client_app, auth_headers, monkeypatch):
        import main as backend_main

        backend_main.dashboard_app.model_service.test_model = AsyncMock(
            return_value={
                "success": True,
                "model": "gpt-4o",
                "latency_ms": 1200,
                "input_tokens": 900,
                "output_tokens": 150,
                "output_tokens_per_sec": 125.0,
                "total_tokens_per_sec": 875.0,
                "finish_reason": "stop",
            }
        )

        response = client_app.post(
            "/api/models/test",
            json={"model": "gpt-4o", "use_saved_config": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["output_tokens_per_sec"] == 125.0

    def test_post_model_test_provider_failure(self, client_app, auth_headers, monkeypatch):
        import main as backend_main

        backend_main.dashboard_app.model_service.test_model = AsyncMock(
            return_value={
                "success": False,
                "model": "gpt-4o",
                "error": "rate limited",
            }
        )

        response = client_app.post(
            "/api/models/test",
            json={"model": "gpt-4o"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "rate limited" in body["error"]
