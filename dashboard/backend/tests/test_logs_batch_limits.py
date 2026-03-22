"""POST /logs/batch limits, WebSocket batching shape."""
import pytest

import main as backend_main


class TestLogBatchLimits:
    def test_batch_rejects_over_max_entries(self, client_app, monkeypatch, auth_headers):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "k", raising=False)
        monkeypatch.setattr(backend_main.settings, "max_log_batch_entries", 3, raising=False)
        payload = {"logs": [{"level": "INFO", "message": str(i), "source": "t"} for i in range(5)]}
        r = client_app.post("/logs/batch", json=payload, headers={"Authorization": "Bearer k"})
        assert r.status_code == 400
        assert "maximum" in (r.json().get("detail") or "").lower()

    def test_batch_accepts_at_max_entries(self, client_app, monkeypatch, auth_headers):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "k", raising=False)
        monkeypatch.setattr(backend_main.settings, "max_log_batch_entries", 5, raising=False)
        payload = {"logs": [{"level": "INFO", "message": str(i), "source": "t"} for i in range(5)]}
        r = client_app.post("/logs/batch", json=payload, headers={"Authorization": "Bearer k"})
        assert r.status_code == 200
        assert r.json().get("count") == 5


class TestLogsBatchWebSocketBroadcast:
    def test_batch_emits_single_logs_batch_message(self, client_app, monkeypatch, auth_headers):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "k", raising=False)
        calls = []

        async def fake_broadcast(message):
            calls.append(message)

        monkeypatch.setattr(backend_main.dashboard_app.websocket_manager, "broadcast", fake_broadcast)

        payload = {
            "logs": [
                {"level": "INFO", "message": "a", "source": "t"},
                {"level": "INFO", "message": "b", "source": "t"},
            ]
        }
        r = client_app.post("/logs/batch", json=payload, headers={"Authorization": "Bearer k"})
        assert r.status_code == 200
        assert len(calls) == 1
        assert calls[0].get("type") == "logs_batch"
        assert isinstance(calls[0].get("data"), list)
        assert len(calls[0]["data"]) == 2

    def test_batch_empty_succeeds_with_zero_count(self, client_app, monkeypatch, auth_headers):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "k", raising=False)
        r = client_app.post("/logs/batch", json={"logs": []}, headers={"Authorization": "Bearer k"})
        assert r.status_code == 200
        assert r.json().get("count") == 0
