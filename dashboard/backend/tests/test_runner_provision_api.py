"""
Tests for action runner connection provision/deprovision APIs (GCP runner VM).
Auth required; connection not found returns 404; deprovision with no VM returns success.
"""
import pytest
import main as backend_main


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

    def test_azure_discovery_endpoint_requires_auth(self, client_app):
        response = client_app.post("/api/azure-devops/discovery", json={"org_url": "https://dev.azure.com/test", "pat": "x"})
        assert response.status_code == 401

    def test_azure_discovery_lists_repos_and_pools(self, client_app, auth_headers, monkeypatch):
        class Resp:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload
                self.content = b"x"

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=0):
            if "_apis/projects" in url:
                return Resp(200, {"value": [{"id": "p1", "name": "Product"}]})
            if "_apis/git/repositories" in url:
                return Resp(200, {"value": [{"id": "r1", "name": "Archive.MDT.ConfigEditor", "webUrl": "https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor"}]})
            if "_apis/distributedtask/pools" in url:
                return Resp(200, {"value": [{"id": 7, "name": "PRAgent_Cloud", "isHosted": False}]})
            return Resp(404, {"message": "not found"})

        import requests
        monkeypatch.setattr(requests, "get", fake_get)

        response = client_app.post(
            "/api/azure-devops/discovery",
            json={"org_url": "https://mdt-software.visualstudio.com", "pat": "pat"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("organization_url") == "https://mdt-software.visualstudio.com"
        assert len(data.get("repositories", [])) == 1
        assert data["repositories"][0]["project"] == "Product"
        assert len(data.get("pools", [])) == 1
        assert data["pools"][0]["name"] == "PRAgent_Cloud"

    def test_provision_azure_auto_selects_pool_when_missing(self, client_app, auth_headers, monkeypatch):
        # Configure minimal GCP settings so endpoint reaches provisioning logic.
        monkeypatch.setattr(backend_main.settings, "gcp_runner_project_id", "test-project", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_region", "us-central1", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_zone", "us-central1-a", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_machine_type", "e2-medium", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_subnet", "", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_prefix", "test-runner", raising=False)
        monkeypatch.setattr(backend_main.settings, "backend_base_url", "http://localhost", raising=False)
        monkeypatch.setattr(backend_main.settings, "pr_agent_config_gcs_bucket", "", raising=False)
        monkeypatch.setattr(backend_main.settings, "pr_agent_config_gcs_prefix", "pr-agent-config/", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_pr_agent_repo_url", "https://github.com/Codium-ai/pr-agent.git", raising=False)
        monkeypatch.setattr(backend_main.settings, "gcp_runner_pr_agent_image", "", raising=False)
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "", raising=False)

        class Resp:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload
                self.content = b"x"

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=0):
            if "_apis/distributedtask/pools" in url:
                return Resp(200, {"value": [{"id": 101, "name": "PRAgent_Cloud", "isHosted": False}]})
            return Resp(404, {"message": "not found"})

        import requests
        monkeypatch.setattr(requests, "get", fake_get)

        from services.gcp_runner_service import GCPRunnerService

        def fake_provision(self, connection_id, provider, organization, project, agent_pool="", ado_org_url=""):
            assert provider == "azure_devops"
            assert agent_pool == "PRAgent_Cloud"
            return {
                "success": True,
                "instance_name": "vm-test",
                "zone": "us-central1-a",
                "message": "ok",
            }

        monkeypatch.setattr(GCPRunnerService, "provision", fake_provision)

        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "azure_devops", "organization": "mdt-software", "project": "Product"},
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]

        create_repo = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/Archive.MDT.ConfigEditor",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor",
                "azure_pat": "pat",
                "action_runner_connection_id": conn_id,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert create_repo.status_code == 200

        response = client_app.post(
            f"/api/action-runner-connections/{conn_id}/provision",
            headers=auth_headers,
        )
        assert response.status_code == 200
        payload = response.json().get("data", {})
        assert payload.get("success") is True
