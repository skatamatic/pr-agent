"""
Tests for action runner connection provision/deprovision APIs (GCP runner VM).
Auth required; connection not found returns 404; deprovision with no VM returns success.
"""
import pytest
from uuid import uuid4
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
        vm_result = data.get("data", {}).get("vm", {})
        assert vm_result.get("success") is True
        assert "message" in vm_result

    def test_delete_connection_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.delete(
            "/api/action-runner-connections/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_delete_connection_removes_record(self, client_app, auth_headers):
        create = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "github", "organization": "del-test-org"},
            headers=auth_headers,
        )
        assert create.status_code == 200
        conn_id = create.json()["data"]["id"]
        response = client_app.delete(
            f"/api/action-runner-connections/{conn_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        payload = response.json().get("data", {})
        assert payload.get("repos_unlinked") is not None
        get_resp = client_app.get("/api/action-runner-connections", headers=auth_headers)
        ids = [c["id"] for c in get_resp.json().get("data", [])]
        assert conn_id not in ids

    def test_delete_connection_unlinks_repos(self, client_app, auth_headers):
        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "azure_devops", "organization": "unlink-org", "project": "Proj"},
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]
        create_repo = client_app.post(
            "/api/repositories",
            json={
                "name": "Proj/UnlinkRepo",
                "provider": "azure_devops",
                "url": "https://dev.azure.com/unlink-org/Proj/_git/UnlinkRepo",
                "action_runner_connection_id": conn_id,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert create_repo.status_code == 200
        repo_id = create_repo.json()["data"]["id"]
        del_resp = client_app.delete(f"/api/action-runner-connections/{conn_id}", headers=auth_headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["repos_unlinked"] == 1
        repo_resp = client_app.get("/api/repositories", headers=auth_headers)
        repo = next((r for r in repo_resp.json().get("data", []) if r["id"] == repo_id), None)
        assert repo is not None
        assert repo.get("action_runner_connection_id") is None

    def test_delete_connection_without_auth_returns_401(self, client_app):
        response = client_app.delete("/api/action-runner-connections/1")
        assert response.status_code == 401

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

    def test_azure_pat_identity_requires_auth(self, client_app):
        response = client_app.post("/api/azure-devops/pat-identity", json={"org_url": "https://dev.azure.com/test", "pat": "x"})
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

    def test_azure_pat_identity_resolves_user(self, client_app, auth_headers, monkeypatch):
        class Resp:
            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload
                self.content = b"x"

            def json(self):
                return self._payload

        def fake_get(url, headers=None, timeout=0):
            if "_apis/connectionData" in url:
                return Resp(200, {
                    "authenticatedUser": {
                        "id": "user-1",
                        "providerDisplayName": "AI Review Bot",
                        "uniqueName": "ai-review-bot@contoso.com",
                        "descriptor": "aad.abc",
                        "subjectKind": "user",
                    }
                })
            return Resp(404, {"message": "not found"})

        import requests
        monkeypatch.setattr(requests, "get", fake_get)

        response = client_app.post(
            "/api/azure-devops/pat-identity",
            json={"org_url": "https://dev.azure.com/mdt-software", "pat": "pat"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("identity", {}).get("display_name") == "AI Review Bot"
        assert data.get("verification", {}).get("review_auth_source") == "AZURE_DEVOPS_PAT"
        assert data.get("verification", {}).get("review_uses_provided_pat") is True

    def test_azure_pipeline_setup_returns_pr_merge_guidance(self, client_app, auth_headers, monkeypatch):
        async def fake_push_yaml_direct(repo_data, content=None, db_session=None):
            return {
                "success": True,
                "yaml_pushed": False,
                "yaml_up_to_date": False,
                "pipeline_created": False,
                "pipeline_id": None,
                "requires_pr_merge": True,
                "pr_number": 42,
                "pr_url": "https://dev.azure.com/test/project/_git/repo/pullrequest/42",
                "branch_name": "pr-agent/update-pipeline-42",
                "message": "Direct push blocked; PR created.",
                "setup_steps": [{"id": "check_shared_pipeline_repo", "label": "Checking for shared pipeline repo", "status": "success"}],
                "cleanup_plan": ["cleanup rule"],
            }

        async def fail_if_policy_called(*args, **kwargs):
            raise AssertionError("ensure_build_policy should not be called when pipeline_id is missing")

        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "push_yaml_direct",
            fake_push_yaml_direct,
        )
        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "ensure_build_policy",
            fail_if_policy_called,
        )

        response = client_app.post(
            "/api/azure-devops/pipeline/setup",
            json={
                "repo_url": "https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor",
                "pat": "pat",
                "branch": "master",
                "is_blocking": False,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("success") is True
        assert data.get("requires_pr_merge") is True
        assert data.get("pr_number") == 42
        assert isinstance(data.get("setup_steps"), list)
        assert isinstance(data.get("cleanup_plan"), list)
        assert data.get("policy_created") is False
        assert data.get("policy_updated") is False

    def test_azure_pipeline_setup_returns_400_when_push_fails(self, client_app, auth_headers, monkeypatch):
        async def fake_push_yaml_direct(repo_data, content=None, db_session=None):
            return {"success": False, "error": "Push failed"}

        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "push_yaml_direct",
            fake_push_yaml_direct,
        )

        response = client_app.post(
            "/api/azure-devops/pipeline/setup",
            json={
                "repo_url": "https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor",
                "pat": "pat",
                "branch": "master",
                "is_blocking": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Push failed" in response.json().get("detail", "")

    def test_azure_pipeline_setup_passes_db_session_to_push_template_resolution(self, client_app, auth_headers, monkeypatch):
        captured = {"db_session_is_none": None}

        async def fake_push_yaml_direct(repo_data, content=None, db_session=None):
            captured["db_session_is_none"] = db_session is None
            return {
                "success": True,
                "yaml_pushed": True,
                "yaml_up_to_date": False,
                "pipeline_created": True,
                "pipeline_id": 123,
                "requires_pr_merge": False,
                "message": "ok",
                "setup_steps": [],
                "cleanup_plan": [],
                "cleanup": {"attempted": False, "actions": []},
            }

        async def fake_ensure_build_policy(repo_data, branch, pipeline_definition_id, is_blocking=False):
            return {"success": True, "created": True, "updated": False}

        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "push_yaml_direct",
            fake_push_yaml_direct,
        )
        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "ensure_build_policy",
            fake_ensure_build_policy,
        )

        response = client_app.post(
            "/api/azure-devops/pipeline/setup",
            json={
                "repo_url": "https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor",
                "pat": "pat",
                "branch": "master",
                "is_blocking": False,
                "action_runner_connection_id": 42,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert captured["db_session_is_none"] is False

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
        monkeypatch.setattr(
            backend_main.settings,
            "gcp_runner_pr_agent_image",
            "us-central1-docker.pkg.dev/test-project/pr-agent/pr-agent:latest",
            raising=False,
        )
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
                "name": f"Product/Archive.MDT.ConfigEditor.{conn_id}",
                "provider": "azure_devops",
                "url": f"https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor.{conn_id}",
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

    def test_provision_azure_requires_runner_image_config(self, client_app, auth_headers, monkeypatch):
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

        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={"provider": "azure_devops", "organization": "mdt-software", "project": "Product"},
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]

        unique = uuid4().hex[:8]
        create_repo = client_app.post(
            "/api/repositories",
            json={
                "name": f"Product/Archive.MDT.ConfigEditor.{conn_id}.{unique}",
                "provider": "azure_devops",
                "url": f"https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor.{conn_id}.{unique}",
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
        assert response.status_code == 400
        assert "GCP_RUNNER_PR_AGENT_IMAGE" in response.json().get("detail", "")

    def test_provision_replaces_existing_running_vm_by_default(self, client_app, auth_headers, monkeypatch):
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
        monkeypatch.setattr(
            backend_main.settings,
            "gcp_runner_pr_agent_image",
            "us-central1-docker.pkg.dev/test-project/pr-agent/pr-agent:latest",
            raising=False,
        )
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "", raising=False)

        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={
                "provider": "azure_devops",
                "organization": "mdt-software",
                "project": "Product",
                "agent_pool": "PRAgent_Cloud",
            },
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]

        create_repo = client_app.post(
            "/api/repositories",
            json={
                "name": f"Product/Archive.MDT.ConfigEditor.replace.{conn_id}",
                "provider": "azure_devops",
                "url": f"https://mdt-software.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor.replace.{conn_id}",
                "azure_pat": "pat",
                "action_runner_connection_id": conn_id,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert create_repo.status_code == 200

        from services.gcp_runner_service import GCPRunnerService

        calls = {"deprovision": 0, "provision": 0}

        def fake_get_instance_status(self, instance_name, zone):
            return "RUNNING" if instance_name == "vm-existing" else None

        def fake_deprovision(self, instance_name, zone):
            calls["deprovision"] += 1
            assert instance_name == "vm-existing"
            return {"success": True, "message": "VM deletion started."}

        def fake_provision(self, connection_id, provider, organization, project, agent_pool="", ado_org_url=""):
            calls["provision"] += 1
            if calls["provision"] == 1:
                return {
                    "success": True,
                    "instance_name": "vm-existing",
                    "zone": "us-central1-a",
                    "message": "ok",
                }
            return {
                "success": True,
                "instance_name": "vm-new",
                "zone": "us-central1-a",
                "message": "ok",
            }

        monkeypatch.setattr(GCPRunnerService, "get_instance_status", fake_get_instance_status)
        monkeypatch.setattr(GCPRunnerService, "deprovision", fake_deprovision)
        monkeypatch.setattr(GCPRunnerService, "provision", fake_provision)

        first_response = client_app.post(
            f"/api/action-runner-connections/{conn_id}/provision",
            headers=auth_headers,
        )
        assert first_response.status_code == 200

        response = client_app.post(
            f"/api/action-runner-connections/{conn_id}/provision",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert calls["deprovision"] == 1
        assert calls["provision"] == 2

    def test_deprovision_attempts_azure_deregister_with_derived_agent_name(self, client_app, auth_headers, monkeypatch):
        org_name = "cleanup-derived-org"
        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={
                "provider": "azure_devops",
                "organization": org_name,
                "project": "Product",
                "agent_pool": "PRAgent_SelfHosted",
            },
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]

        create_repo = client_app.post(
            "/api/repositories",
            json={
                "name": f"Product/Archive.MDT.ConfigEditor.{conn_id}",
                "provider": "azure_devops",
                "url": f"https://{org_name}.visualstudio.com/Product/_git/Archive.MDT.ConfigEditor.{conn_id}",
                "azure_pat": "pat-from-linked-repo",
                "action_runner_connection_id": conn_id,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert create_repo.status_code == 200

        captured = {}

        def fake_deregister(org_url, pat, pool_name, agent_name, timeout=20):
            captured["org_url"] = org_url
            captured["pat"] = pat
            captured["pool_name"] = pool_name
            captured["agent_name"] = agent_name
            return {"success": True, "message": "removed"}

        monkeypatch.setattr(backend_main.dashboard_app, "_deregister_azure_agent", fake_deregister)

        response = client_app.post(
            f"/api/action-runner-connections/{conn_id}/deprovision",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("azure_agent", {}).get("success") is True
        assert captured.get("pat") == "pat-from-linked-repo"
        assert captured.get("pool_name") == "PRAgent_SelfHosted"
        assert str(conn_id) in (captured.get("agent_name") or "")

    def test_delete_connection_uses_org_pat_fallback_for_agent_deregister(self, client_app, auth_headers, monkeypatch):
        org_name = "cleanup-fallback-org"
        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={
                "provider": "azure_devops",
                "organization": org_name,
                "project": "Product",
                "agent_pool": "PRAgent_SelfHosted",
            },
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]

        linked_repo = client_app.post(
            "/api/repositories",
            json={
                "name": f"Product/NoPatRepo.{conn_id}",
                "provider": "azure_devops",
                "url": f"https://{org_name}.visualstudio.com/Product/_git/NoPatRepo.{conn_id}",
                "action_runner_connection_id": conn_id,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert linked_repo.status_code == 200

        fallback_repo = client_app.post(
            "/api/repositories",
            json={
                "name": f"Product/PatRepo.{conn_id}",
                "provider": "azure_devops",
                "url": f"https://{org_name}.visualstudio.com/Product/_git/PatRepo.{conn_id}",
                "azure_pat": "pat-from-org-fallback",
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert fallback_repo.status_code == 200

        captured = {}

        def fake_deregister(org_url, pat, pool_name, agent_name, timeout=20):
            captured["pat"] = pat
            captured["pool_name"] = pool_name
            captured["agent_name"] = agent_name
            return {"success": True, "message": "removed"}

        monkeypatch.setattr(backend_main.dashboard_app, "_deregister_azure_agent", fake_deregister)

        response = client_app.delete(
            f"/api/action-runner-connections/{conn_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("azure_agent", {}).get("success") is True
        assert captured.get("pat") == "pat-from-org-fallback"
        assert captured.get("pool_name") == "PRAgent_SelfHosted"

    def test_delete_connection_attempts_agent_deregister_even_without_pool(self, client_app, auth_headers, monkeypatch):
        org_name = "cleanup-no-pool-org"
        create_conn = client_app.post(
            "/api/action-runner-connections",
            json={
                "provider": "azure_devops",
                "organization": org_name,
                "project": "Product",
                # intentionally no agent_pool configured
            },
            headers=auth_headers,
        )
        assert create_conn.status_code == 200
        conn_id = create_conn.json()["data"]["id"]

        linked_repo = client_app.post(
            "/api/repositories",
            json={
                "name": f"Product/CleanupNoPool.{conn_id}",
                "provider": "azure_devops",
                "url": f"https://{org_name}.visualstudio.com/Product/_git/CleanupNoPool.{conn_id}",
                "azure_pat": "pat-linked",
                "action_runner_connection_id": conn_id,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert linked_repo.status_code == 200

        captured = {}

        def fake_deregister(org_url, pat, pool_name, agent_name, timeout=20):
            captured["pat"] = pat
            captured["pool_name"] = pool_name
            captured["agent_name"] = agent_name
            return {"success": True, "message": "removed"}

        monkeypatch.setattr(backend_main.dashboard_app, "_deregister_azure_agent", fake_deregister)

        response = client_app.delete(
            f"/api/action-runner-connections/{conn_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json().get("data", {})
        assert data.get("azure_agent", {}).get("success") is True
        assert captured.get("pat") == "pat-linked"
        assert captured.get("pool_name") == ""
        assert str(conn_id) in (captured.get("agent_name") or "")
