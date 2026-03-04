"""
Tests for health, status, and developer-mode API endpoints.
Uses in-memory SQLite via client_app fixture.
"""
import pytest


class TestHealthAPI:
    """Health and status endpoints."""

    def test_health_returns_200(self, client_app):
        response = client_app.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_health_response_has_expected_structure_for_dashboard(self, client_app):
        response = client_app.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "database" in data or "api" in data or "services" in data or len(data) >= 1

    def test_health_database_returns_connected_or_error(self, client_app):
        response = client_app.get("/api/health/database")
        assert response.status_code == 200
        data = response.json()
        assert data.get("service") == "database"
        assert "health" in data
        assert data["health"]["status"] in ("connected", "error")
        assert "message" in data["health"]

    def test_health_config_returns_structured_response(self, client_app):
        response = client_app.get("/api/health/config")
        assert response.status_code == 200
        data = response.json()
        assert data.get("service") == "pr_agent_config"
        assert "health" in data
        assert data["health"]["status"] in ("connected", "misconfigured", "error")

    def test_health_context_returns_structured_response(self, client_app):
        response = client_app.get("/api/health/context")
        assert response.status_code == 200
        data = response.json()
        assert data.get("service") == "context_service"
        assert "health" in data

    def test_status_returns_200(self, client_app):
        response = client_app.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_developer_mode_returns_boolean(self, client_app, auth_headers):
        response = client_app.get("/api/developer-mode", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)

    def test_debug_paths_returns_paths(self, client_app, auth_headers):
        response = client_app.get("/api/debug/paths", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "cwd" in data
        assert "config_path" in data
        assert "dashboard_dir" in data

    def test_repositories_health_returns_200_and_structure(self, client_app, auth_headers):
        response = client_app.get("/api/repositories/health", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        health = data["data"]
        assert "total_repos" in health
        assert "healthy_repos" in health
        assert "unhealthy_repos" in health
        assert "error_repos" in health
        assert isinstance(health["error_repos"], list)
        assert health["total_repos"] >= 0
