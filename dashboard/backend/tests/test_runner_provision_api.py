"""
Tests for action runner connection provision/deprovision APIs (GCP runner VM).
Auth required; connection not found returns 404; deprovision with no VM returns success.
"""
import pytest


class TestRunnerProvisionAPI:
    """Provision and deprovision runner VM endpoints."""

    def test_provision_without_auth_returns_401(self, client_app):
        response = client_app.post("/api/action-runner-connections/1/provision")
        assert response.status_code == 401

    def test_deprovision_without_auth_returns_401(self, client_app):
        response = client_app.post("/api/action-runner-connections/1/deprovision")
        assert response.status_code == 401

    def test_provision_status_without_auth_returns_401(self, client_app):
        response = client_app.get("/api/action-runner-connections/1/provision-status")
        assert response.status_code == 401

    def test_azure_pools_without_auth_returns_401(self, client_app):
        response = client_app.get("/api/action-runner-connections/1/azure-agent-pools")
        assert response.status_code == 401

    def test_provision_connection_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.post(
            "/api/action-runner-connections/99999/provision",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_provision_status_connection_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.get(
            "/api/action-runner-connections/99999/provision-status",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_azure_pools_connection_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.get(
            "/api/action-runner-connections/99999/azure-agent-pools",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_provision_gcp_not_configured_returns_400(self, client_app, auth_headers):
        """When GCP_RUNNER_PROJECT_ID is not set, provision returns 400 with a clear message."""
        create = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "github", "organization": "test-org"},
            headers=auth_headers,
        )
        assert create.status_code == 200
        conn_id = create.json()["data"]["id"]
        response = client_app.post(
            f"/api/action-runner-connections/{conn_id}/provision",
            headers=auth_headers,
        )
        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "GCP" in detail or "configured" in detail.lower()

    def test_deprovision_connection_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.post(
            "/api/action-runner-connections/99999/deprovision",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_deprovision_no_vm_returns_success(self, client_app, auth_headers):
        # Create a connection (no VM provisioned)
        create = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "github", "organization": "other-org"},
            headers=auth_headers,
        )
        assert create.status_code == 200
        conn_id = create.json()["data"]["id"]
        response = client_app.post(
            f"/api/action-runner-connections/{conn_id}/deprovision",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("data", {}).get("success") is True
        assert "message" in data.get("data", {})

    def test_provision_status_no_vm_returns_not_complete(self, client_app, auth_headers):
        create = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "github", "organization": "status-org"},
            headers=auth_headers,
        )
        assert create.status_code == 200
        conn_id = create.json()["data"]["id"]

        response = client_app.get(
            f"/api/action-runner-connections/{conn_id}/provision-status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        payload = response.json().get("data", {})
        assert payload.get("complete") is False
        assert payload.get("vm_running") is False
