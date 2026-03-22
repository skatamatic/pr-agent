import pytest
import main as backend_main


class TestRouteAuthHardening:
    def test_admin_export_requires_auth(self, client_app):
        response = client_app.post("/api/admin/database/export", json={"format": "json"})
        assert response.status_code == 401

    def test_dev_route_requires_auth(self, client_app):
        response = client_app.post("/api/dev/simulate-activity")
        assert response.status_code == 401


class TestWebSocketAuth:
    def test_websocket_connects_with_jwt_query_token(self, client_app, auth_headers):
        token = auth_headers["Authorization"].split(" ", 1)[1]
        with client_app.websocket_connect(f"/ws?token={token}") as ws:
            message = ws.receive_json()
            assert message.get("type") == "welcome"

    def test_websocket_rejects_without_auth(self, client_app):
        with pytest.raises(Exception):
            with client_app.websocket_connect("/ws"):
                pass


class TestIngestApiKeyAuth:
    def test_ingest_allows_dashboard_api_key(self, client_app, monkeypatch):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "ingest-test-key", raising=False)
        response = client_app.post(
            "/logs/immediate",
            json={"level": "INFO", "message": "ingest test"},
            headers={"Authorization": "Bearer ingest-test-key"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("id") is not None
        assert body.get("status") == "received"

    def test_ingest_rejects_anonymous_when_no_api_key(self, client_app, monkeypatch):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "", raising=False)
        response = client_app.post("/logs/immediate", json={"message": "no auth"})
        assert response.status_code == 401
        assert "Set DASHBOARD_API_KEY" in (response.json().get("detail") or "")

    def test_ingest_rejects_wrong_api_key(self, client_app, monkeypatch):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "correct-ingest-key", raising=False)
        response = client_app.post(
            "/logs/immediate",
            json={"level": "INFO", "message": "bad key"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert response.status_code == 401
        assert "Authentication required" in (response.json().get("detail") or "")

    def test_batch_ingest_allows_dashboard_api_key(self, client_app, monkeypatch):
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "batch-ingest-key", raising=False)
        response = client_app.post(
            "/logs/batch",
            json={"logs": [{"level": "INFO", "message": "batch via key", "source": "test"}]},
            headers={"Authorization": "Bearer batch-ingest-key"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("status") == "received"
        assert body.get("count") == 1
