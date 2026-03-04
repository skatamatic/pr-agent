"""
Tests for config API: get config, pr-agent-path (read and validate), bulk-upload.
"""
import io
import zipfile
import pytest


class TestConfigAPI:
    """Configuration endpoints (require auth)."""

    def test_get_config_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], dict)

    def test_get_pr_agent_path_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/config/pr-agent-path", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        d = data["data"]
        assert "config_path" in d
        assert "source" in d
        assert "validation" in d

    def test_validate_pr_agent_path_empty_returns_400(self, client_app, auth_headers):
        response = client_app.post(
            "/api/config/pr-agent-path/validate",
            json={"path": ""},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Path is required" in response.json().get("detail", "")

    def test_validate_pr_agent_path_with_path_returns_200(self, client_app, auth_headers):
        response = client_app.post(
            "/api/config/pr-agent-path/validate",
            json={"path": "/some/path"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "valid" in data["data"]


class TestConfigAPIAuthRequired:
    """Endpoints that require auth: use auth_headers."""

    def test_get_config_with_auth_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        config = data["data"]
        if "csharp_code_context_service" in config:
            ctx = config["csharp_code_context_service"]
            if ctx.get("username"):
                assert ctx["username"] == "***"
            if ctx.get("password"):
                assert ctx["password"] == "***"

    def test_bulk_upload_without_auth_returns_401(self, client_app):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("configuration.toml", "[config]\nmodel = 'test'")
        buf.seek(0)
        response = client_app.post(
            "/api/config/bulk-upload",
            files={"file": ("config.zip", buf, "application/zip")},
        )
        assert response.status_code == 401

    def test_bulk_upload_requires_zip(self, client_app, auth_headers):
        response = client_app.post(
            "/api/config/bulk-upload",
            files={"file": ("notzip.txt", io.BytesIO(b"hello"), "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "zip" in response.json().get("detail", "").lower()

    def test_bulk_upload_with_zip_extracts_and_stores(self, client_app, auth_headers):
        """ZIP is extracted; individual file contents are stored (no ZIP stored)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("configuration.toml", "[config]\nmodel = 'bulk-test-model'")
            zf.writestr("csharp_code_context.config.toml", "[csharp_code_context_service]\nenabled = false\nurl = ''")
        buf.seek(0)
        response = client_app.post(
            "/api/config/bulk-upload",
            files={"file": ("config.zip", buf, "application/zip")},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("data", {}).get("status") == "success"
        assert "message" in data
        get_resp = client_app.get("/api/config", headers=auth_headers)
        assert get_resp.status_code == 200
        config = get_resp.json()["data"]
        assert config.get("config", {}).get("model") == "bulk-test-model"
        assert config.get("csharp_code_context_service", {}).get("enabled") is False

    def test_bulk_upload_empty_zip_returns_400(self, client_app, auth_headers):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("readme.txt", "no config files")
        buf.seek(0)
        response = client_app.post(
            "/api/config/bulk-upload",
            files={"file": ("empty.zip", buf, "application/zip")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "contain" in response.json().get("detail", "").lower()
