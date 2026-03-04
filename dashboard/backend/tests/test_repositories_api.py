"""
Tests for repositories API: list, names, create, get by id (and 404).
"""
import pytest


class TestRepositoriesAPI:
    """Repository CRUD and list endpoints."""

    def test_get_repositories_requires_auth(self, client_app):
        response = client_app.get("/api/repositories")
        assert response.status_code == 401

    def test_get_repositories_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/repositories", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_get_repositories_names_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/repositories/names", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_post_repositories_create_minimal(self, client_app, auth_headers):
        payload = {
            "name": "test-org/audit-repo",
            "provider": "github",
            "url": "https://github.com/test-org/audit-repo",
            "is_active": True,
        }
        response = client_app.post("/api/repositories", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        repo = data["data"]
        assert repo["name"] == payload["name"]
        assert repo["provider"] == payload["provider"]
        assert repo["url"] == payload["url"]

    def test_get_repository_by_id_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.get("/api/repositories/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_get_repositories_health_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/repositories/health", headers=auth_headers)
        assert response.status_code == 200

    def test_get_action_runner_connections_requires_auth(self, client_app):
        response = client_app.get("/api/action-runner-connections")
        assert response.status_code == 401

    def test_get_action_runner_connections_returns_200_and_list(self, client_app, auth_headers):
        response = client_app.get("/api/action-runner-connections", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        for conn in data["data"]:
            assert "gcp_instance_name" in conn
            assert "gcp_zone" in conn

    def test_post_action_runner_connection_creates_and_returns_201_or_200(self, client_app, auth_headers):
        payload = {
            "provider": "azure_devops",
            "organization": "my-org",
            "project": "MyProject",
            "display_name": "MyOrg (ADO)",
        }
        response = client_app.post("/api/action-runner-connections", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        conn = data["data"]
        assert conn["provider"] == "azure_devops"
        assert conn["organization"] == "my-org"
        assert conn["project"] == "MyProject"
        assert "id" in conn
        assert conn.get("repository_count") == 0
        assert "gcp_instance_name" in conn
        assert "gcp_zone" in conn
