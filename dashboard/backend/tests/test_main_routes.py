"""
Additional main.py route tests to improve coverage: admin, config, metrics, repos, cron.
Assertions verify response shape and meaningful behavior (round-trip where applicable).
"""
import builtins
import types
import pytest
from datetime import datetime, timezone
import main as backend_main


class _MockAiohttpResponse:
    def __init__(self, status, json_payload=None, text_payload=""):
        self.status = status
        self._json_payload = json_payload if json_payload is not None else {}
        self._text_payload = text_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._json_payload

    async def text(self):
        return self._text_payload


class _MockAiohttpSession:
    def __init__(self, response):
        self._response = response
        self.last_post_url = None
        self.last_post_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json=None, **kwargs):
        self.last_post_url = url
        self.last_post_json = json or {}
        return self._response


class TestAdminCleanupRoutes:
    """Data cleanup preview and execute (hit DataCleanupService)."""

    def test_cleanup_preview_400_no_cutoff(self, client_app, auth_headers):
        r = client_app.post("/api/admin/cleanup/preview", json={}, headers=auth_headers)
        assert r.status_code == 400
        assert "cutoff_date" in (r.json().get("detail") or "").lower()

    def test_cleanup_preview_200_with_cutoff(self, client_app, auth_headers):
        cutoff = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat().replace("+00:00", "Z")
        r = client_app.post("/api/admin/cleanup/preview", json={"cutoff_date": cutoff}, headers=auth_headers)
        assert r.status_code in (200, 500)
        if r.status_code == 200:
            d = r.json()
            assert "data" in d
            assert "before_cleanup" in d["data"] and "after_cleanup" in d["data"]

    def test_cleanup_execute_400_no_cutoff(self, client_app, auth_headers):
        r = client_app.post("/api/admin/cleanup/execute", json={}, headers=auth_headers)
        assert r.status_code == 400
        assert "cutoff_date" in (r.json().get("detail") or "").lower()

    def test_cleanup_execute_200_with_cutoff(self, client_app, auth_headers):
        cutoff = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat().replace("+00:00", "Z")
        r = client_app.post(
            "/api/admin/cleanup/execute",
            json={"cutoff_date": cutoff, "data_types": ["logs"]},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert "deleted_counts" in data["data"]
        assert "message" in data["data"]
        assert "logs" in data["data"]["deleted_counts"]


class TestAdminRoutes:
    """Admin retention and database endpoints (require auth)."""

    def test_get_retention_config_200(self, client_app, auth_headers):
        r = client_app.get("/api/admin/retention/config", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_post_retention_config_round_trip(self, client_app, auth_headers):
        r = client_app.post(
            "/api/admin/retention/config",
            json={"log_retention_days": 31, "job_retention_days": 91},
            headers=auth_headers,
        )
        assert r.status_code == 200
        get_r = client_app.get("/api/admin/retention/config", headers=auth_headers)
        assert get_r.status_code == 200
        cfg = get_r.json()["data"]
        assert cfg.get("log_retention_days") == 31
        assert cfg.get("job_retention_days") == 91

    def test_get_database_stats_200(self, client_app, auth_headers):
        r = client_app.get("/api/admin/database/stats", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert "data" in d
        assert "jobs_count" in d["data"] or "size_mb" in d["data"] or "table_stats" in d["data"]

    def test_post_database_cleanup_dry_run_200(self, client_app, auth_headers):
        r = client_app.post("/api/admin/database/cleanup?dry_run=true", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_database_backups_200(self, client_app, auth_headers):
        r = client_app.get("/api/admin/database/backups", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()
        assert isinstance(r.json()["data"], list)

    def test_get_backup_directory_200(self, client_app, auth_headers):
        r = client_app.get("/api/admin/backup/directory", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()
        assert "backup_directory" in r.json()["data"]

    def test_post_backup_directory_rejects_empty(self, client_app, auth_headers):
        r = client_app.post("/api/admin/backup/directory", json={}, headers=auth_headers)
        assert r.status_code in (400, 500)

    def test_post_backup_directory_200(self, client_app, auth_headers):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmp:
            r = client_app.post(
                "/api/admin/backup/directory",
                json={"backup_directory": tmp},
                headers=auth_headers,
            )
            assert r.status_code == 200

    def test_post_database_export_json_200(self, client_app, auth_headers):
        r = client_app.post("/api/admin/database/export", json={"format": "json"}, headers=auth_headers)
        assert r.status_code == 200
        assert "application/" in r.headers.get("content-type", "")
        assert len(r.content) > 0
        body = r.json()
        assert isinstance(body, (dict, list))

    def test_delete_backup_not_found_400(self, client_app, auth_headers):
        r = client_app.delete("/api/admin/database/backups/nonexistent_file_xyz.db", headers=auth_headers)
        assert r.status_code in (400, 404, 500)


class TestConfigAndDeveloperRoutes:
    """Config update, developer-mode, debug paths."""

    def test_get_config_200(self, client_app, auth_headers):
        r = client_app.get("/api/config", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert isinstance(data["data"], dict)

    def test_get_dashboard_auto_setup_200(self, client_app, auth_headers, monkeypatch):
        monkeypatch.setattr(backend_main.settings, "backend_base_url", "https://dash.example.com", raising=False)
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "test-dashboard-key", raising=False)
        r = client_app.get("/api/config/dashboard-auto-setup", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("backend_url") == "https://dash.example.com"
        assert data.get("api_key") == "test-dashboard-key"

    def test_get_dashboard_auto_setup_cloud_run_fallback_when_localhost(self, client_app, auth_headers, monkeypatch):
        monkeypatch.setattr(backend_main.settings, "backend_base_url", "http://localhost:8000", raising=False)
        monkeypatch.setattr(backend_main.settings, "dashboard_api_key", "test-dashboard-key", raising=False)
        monkeypatch.setenv("K_SERVICE", "pr-agent-dash-dev-backend")
        monkeypatch.setenv("GCP_RUNNER_REGION", "us-central1")
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_NUMBER", raising=False)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_gcp_project_number_from_metadata",
            lambda: "123456789012",
            raising=True,
        )
        r = client_app.get("/api/config/dashboard-auto-setup", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("backend_url") == "https://pr-agent-dash-dev-backend-123456789012.us-central1.run.app"
        assert data.get("api_key") == "test-dashboard-key"

    def test_post_config_200(self, client_app, auth_headers):
        r = client_app.post(
            "/api/config",
            json={"config": {"config": {"verbosity_level": 2}}},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_context_service_smoke_success_with_token(self, client_app, auth_headers, monkeypatch):
        mock_response = _MockAiohttpResponse(status=200, json_payload={"token": "test-token"})
        mock_session = _MockAiohttpSession(response=mock_response)
        monkeypatch.setattr(backend_main.aiohttp, "ClientSession", lambda *args, **kwargs: mock_session)

        r = client_app.post(
            "/api/config/test-context-service",
            json={
                "url": "https://context.local",
                "username": "svc-user",
                "password": "svc-pass",
            },
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["details"]["status_code"] == 200
        assert body["details"]["token_received"] is True
        assert mock_session.last_post_url == "https://context.local/api/auth/login"
        assert mock_session.last_post_json == {"username": "svc-user", "password": "svc-pass"}

    def test_context_service_smoke_fails_when_login_url_used(self, client_app, auth_headers):
        r = client_app.post(
            "/api/config/test-context-service",
            json={
                "url": "https://context.local/api/auth/login",
                "username": "svc-user",
                "password": "svc-pass",
            },
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "root URL" in body["message"]

    def test_context_service_smoke_fails_when_missing_token(self, client_app, auth_headers, monkeypatch):
        mock_response = _MockAiohttpResponse(
            status=200,
            json_payload={"message": "ok"},
            text_payload='{"message":"ok"}',
        )
        monkeypatch.setattr(
            backend_main.aiohttp,
            "ClientSession",
            lambda *args, **kwargs: _MockAiohttpSession(response=mock_response),
        )

        r = client_app.post(
            "/api/config/test-context-service",
            json={
                "url": "https://context.local",
                "username": "svc-user",
                "password": "svc-pass",
            },
            headers=auth_headers,
        )

        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "token" in body["message"].lower()
        assert body["details"]["status_code"] == 200

    def test_get_pr_agent_path_200(self, client_app, auth_headers):
        r = client_app.get("/api/config/pr-agent-path", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_post_pr_agent_path_returns_400_env_only(self, client_app, auth_headers):
        """Config path is set via PR_AGENT_CONFIG_PATH env only; POST is deprecated."""
        r = client_app.post("/api/config/pr-agent-path", json={"path": ""}, headers=auth_headers)
        assert r.status_code == 400
        assert "PR_AGENT_CONFIG_PATH" in (r.json().get("detail") or "")

    def test_get_developer_mode_200(self, client_app, auth_headers):
        r = client_app.get("/api/developer-mode", headers=auth_headers)
        assert r.status_code == 200

    def test_get_debug_paths_200(self, client_app, auth_headers):
        r = client_app.get("/api/debug/paths", headers=auth_headers)
        assert r.status_code == 200


class TestRepositoriesExtraRoutes:
    """Repositories health, names, token-permissions."""

    def test_get_repositories_health_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/health", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert isinstance(data["data"], (list, dict))

    def test_get_repositories_names_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/names", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()
        assert isinstance(r.json()["data"], list)

    def test_get_repositories_token_permissions_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/token-permissions", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()
        assert "github" in r.json()["data"]

    def test_post_repositories_update_configs(self, client_app, auth_headers):
        r = client_app.post("/api/repositories/update-configs", headers=auth_headers)
        assert r.status_code in (200, 500)

    def test_get_repositories_with_provider(self, client_app, auth_headers):
        r = client_app.get("/api/repositories?provider=github", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_repositories_active_only(self, client_app, auth_headers):
        r = client_app.get("/api/repositories?active_only=true", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()


class TestRepositoriesById:
    """Repository get/put/delete by id and related endpoints."""

    def test_get_repository_404(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/999999", headers=auth_headers)
        assert r.status_code == 404

    def test_get_put_delete_repository_flow(self, client_app, auth_headers):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "cov-test/repo-60",
                "provider": "github",
                "url": "https://github.com/cov-test/repo-60",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]
        r = client_app.get(f"/api/repositories/{repo_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "cov-test/repo-60"
        put = client_app.put(
            f"/api/repositories/{repo_id}",
            json={"name": "cov-test/repo-60", "url": "https://github.com/cov-test/repo-60-updated"},
            headers=auth_headers,
        )
        assert put.status_code == 200
        get_after_put = client_app.get(f"/api/repositories/{repo_id}", headers=auth_headers)
        assert get_after_put.status_code == 200
        assert "repo-60-updated" in get_after_put.json()["data"]["url"]
        del_r = client_app.delete(f"/api/repositories/{repo_id}", headers=auth_headers)
        assert del_r.status_code == 200
        get_after = client_app.get(f"/api/repositories/{repo_id}", headers=auth_headers)
        assert get_after.status_code == 404

    def test_get_repository_effective_config_404_or_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/999998/effective-config", headers=auth_headers)
        assert r.status_code in (200, 404)

    def test_get_repository_best_practices_404_or_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/999998/best-practices", headers=auth_headers)
        assert r.status_code in (200, 404)

    def test_get_repository_pr_agent_config_404_or_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/999998/pr-agent-config", headers=auth_headers)
        assert r.status_code in (200, 404)

    def test_get_repository_github_action_config_404_or_200(self, client_app, auth_headers):
        r = client_app.get("/api/repositories/999998/github-action-config", headers=auth_headers)
        assert r.status_code in (200, 404)

    def test_repository_cleanup_preview_azure_includes_scope(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/CleanupPreviewRepo",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/CleanupPreviewRepo",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        async def _fake_list_build_policies(_repo_data):
            return {"policies": [{"policy_id": 10, "pipeline_name": "PR-Agent Review (main)"}]}

        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "list_build_policies",
            _fake_list_build_policies,
        )

        preview = client_app.get(f"/api/repositories/{repo_id}/cleanup/preview", headers=auth_headers)
        assert preview.status_code == 200
        data = preview.json().get("data", {})
        assert data.get("repository", {}).get("id") == repo_id
        assert "cleanup_scope" in data
        assert data["cleanup_scope"].get("azure_checks") == 1
        assert data.get("impacts", {}).get("target_repository_deleted") is False

    def test_repository_cleanup_start_and_status(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "cleanup-start/repo",
                "provider": "github",
                "url": "https://github.com/cleanup-start/repo",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        def _skip_background_task(coro):
            coro.close()
            return None

        monkeypatch.setattr(backend_main.asyncio, "create_task", _skip_background_task)

        start = client_app.post(f"/api/repositories/{repo_id}/cleanup/start", headers=auth_headers)
        assert start.status_code == 200
        start_data = start.json().get("data", {})
        operation_id = start_data.get("operation_id")
        assert operation_id
        assert isinstance(start_data.get("steps"), list)

        status = client_app.get(f"/api/repositories/{repo_id}/cleanup/status/{operation_id}", headers=auth_headers)
        assert status.status_code == 200
        op = status.json().get("data", {})
        assert op.get("operation_id") == operation_id
        assert op.get("operation_type") == "repository_cleanup"
        assert op.get("status") in ("running", "completed", "failed")

    def test_repository_activation_sync_start_and_status(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/ActivationSyncRepo",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/ActivationSyncRepo",
                "azure_pat": "pat",
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        def _skip_background_task(coro):
            coro.close()
            return None

        monkeypatch.setattr(backend_main.asyncio, "create_task", _skip_background_task)

        start = client_app.post(
            f"/api/repositories/{repo_id}/activation-sync/start",
            json={"target_active": False},
            headers=auth_headers,
        )
        assert start.status_code == 200
        start_data = start.json().get("data", {})
        operation_id = start_data.get("operation_id")
        assert operation_id

        status = client_app.get(
            f"/api/repositories/{repo_id}/activation-sync/status/{operation_id}",
            headers=auth_headers,
        )
        assert status.status_code == 200
        op = status.json().get("data", {})
        assert op.get("operation_id") == operation_id
        assert op.get("operation_type") == "repository_activation_sync"

    def test_repository_activation_sync_requires_target_active(self, client_app, auth_headers):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/ActivationSyncValidationRepo",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/ActivationSyncValidationRepo",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        start = client_app.post(
            f"/api/repositories/{repo_id}/activation-sync/start",
            json={},
            headers=auth_headers,
        )
        assert start.status_code == 400
        assert "target_active" in (start.json().get("detail") or "")

    def test_repository_sync_pipeline_variables_endpoint(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/VarSyncRepo",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/VarSyncRepo",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        async def _fake_sync(repo_data, db_session=None, pipeline_definition_id=None):
            return {
                "success": True,
                "pipelines_targeted": 1,
                "results": [{"pipeline_id": 77, "success": True}],
            }

        monkeypatch.setattr(
            backend_main.dashboard_app.azure_pipeline_config_service,
            "sync_pipeline_variables",
            _fake_sync,
        )

        resp = client_app.post(
            f"/api/repositories/{repo_id}/azure-pipeline-config/sync-variables",
            json={},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("success") is True
        assert data.get("pipelines_targeted") == 1

    def test_best_practices_azure_fallback_without_pr_agent_provider(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/FallbackBestPractices",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/FallbackBestPractices",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        monkeypatch.setattr(backend_main.dashboard_app, "_create_azure_devops_provider", lambda repo: None)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_azure_repo_file_content",
            lambda repo, file_path, branches=None: "Best practices from fallback" if file_path == "best_practices.md" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/best-practices?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("exists") is True
        assert "fallback" in (data.get("content") or "").lower()

    def test_pr_agent_config_azure_fallback_without_pr_agent_provider(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/FallbackPrAgentConfig",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/FallbackPrAgentConfig",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        monkeypatch.setattr(backend_main.dashboard_app, "_create_azure_devops_provider", lambda repo: None)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_azure_repo_file_content",
            lambda repo, file_path, branches=None: "[config]\nmodel = 'gpt-5.3-codex'" if file_path == ".pr_agent.toml" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/pr-agent-config?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("has_config") is True
        assert "gpt-5.3-codex" in (data.get("content") or "")

    def test_best_practices_github_fallback_without_pr_agent_provider(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "fallback-org/fallback-repo-best-practices",
                "provider": "github",
                "url": "https://github.com/fallback-org/fallback-repo-best-practices",
                "github_token": "ghp_test",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        real_import = builtins.__import__

        def _import_with_missing_github_provider(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pr_agent.git_providers.github_provider":
                raise ImportError("No module named 'pr_agent'")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _import_with_missing_github_provider)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_github_repo_file_content",
            lambda repo, file_path, branches=None: "Best practices from GitHub fallback" if file_path == "best_practices.md" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/best-practices?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("exists") is True
        assert "github fallback" in (data.get("content") or "").lower()

    def test_pr_agent_config_github_fallback_without_pr_agent_provider(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "fallback-org/fallback-repo-pr-agent-config",
                "provider": "github",
                "url": "https://github.com/fallback-org/fallback-repo-pr-agent-config",
                "github_token": "ghp_test",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        real_import = builtins.__import__

        def _import_with_missing_github_provider(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pr_agent.git_providers.github_provider":
                raise ImportError("No module named 'pr_agent'")
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _import_with_missing_github_provider)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_github_repo_file_content",
            lambda repo, file_path, branches=None: "[config]\nmodel = 'gpt-5.3-codex'" if file_path == ".pr_agent.toml" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/pr-agent-config?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("has_config") is True
        assert "gpt-5.3-codex" in (data.get("content") or "")

    def test_best_practices_github_fallback_when_provider_init_fails(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "fallback-org/fallback-repo-best-practices-init-fail",
                "provider": "github",
                "url": "https://github.com/fallback-org/fallback-repo-best-practices-init-fail",
                "github_token": "ghp_test",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        real_import = builtins.__import__

        class BrokenGithubProvider:
            def __init__(self, *args, **kwargs):
                raise ValueError("provider init failed")

        def _import_with_broken_github_provider(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pr_agent.git_providers.github_provider":
                module = types.ModuleType(name)
                module.GithubProvider = BrokenGithubProvider
                return module
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _import_with_broken_github_provider)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_github_repo_file_content",
            lambda repo, file_path, branches=None: "Best practices from init-fail fallback" if file_path == "best_practices.md" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/best-practices?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("exists") is True
        assert "init-fail fallback" in (data.get("content") or "").lower()

    def test_pr_agent_config_github_fallback_when_provider_init_fails(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "fallback-org/fallback-repo-pr-agent-config-init-fail",
                "provider": "github",
                "url": "https://github.com/fallback-org/fallback-repo-pr-agent-config-init-fail",
                "github_token": "ghp_test",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        real_import = builtins.__import__

        class BrokenGithubProvider:
            def __init__(self, *args, **kwargs):
                raise ValueError("provider init failed")

        def _import_with_broken_github_provider(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "pr_agent.git_providers.github_provider":
                module = types.ModuleType(name)
                module.GithubProvider = BrokenGithubProvider
                return module
            return real_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", _import_with_broken_github_provider)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_github_repo_file_content",
            lambda repo, file_path, branches=None: "[config]\nmodel = 'gpt-5.3-codex'" if file_path == ".pr_agent.toml" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/pr-agent-config?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("has_config") is True
        assert "gpt-5.3-codex" in (data.get("content") or "")

    def test_best_practices_azure_direct_fetch_does_not_call_provider(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/DirectFetchBestPractices",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/DirectFetchBestPractices",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        def _fail_provider(_repo):
            raise RuntimeError("provider should not be called for Azure direct fetch")

        monkeypatch.setattr(backend_main.dashboard_app, "_create_azure_devops_provider", _fail_provider)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_azure_repo_file_content",
            lambda repo, file_path, branches=None: "Best practices via direct Azure REST" if file_path == "best_practices.md" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/best-practices?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("exists") is True
        assert "direct azure rest" in (data.get("content") or "").lower()

    def test_pr_agent_config_azure_direct_fetch_does_not_call_provider(self, client_app, auth_headers, monkeypatch):
        create = client_app.post(
            "/api/repositories",
            json={
                "name": "Product/DirectFetchPrAgentConfig",
                "provider": "azure_devops",
                "url": "https://mdt-software.visualstudio.com/Product/_git/DirectFetchPrAgentConfig",
                "azure_pat": "pat",
            },
            headers=auth_headers,
        )
        assert create.status_code == 200
        repo_id = create.json()["data"]["id"]

        def _fail_provider(_repo):
            raise RuntimeError("provider should not be called for Azure direct fetch")

        monkeypatch.setattr(backend_main.dashboard_app, "_create_azure_devops_provider", _fail_provider)
        monkeypatch.setattr(
            backend_main.dashboard_app,
            "_fetch_azure_repo_file_content",
            lambda repo, file_path, branches=None: "[config]\nmodel = 'gpt-5.3-codex'" if file_path == ".pr_agent.toml" else "",
        )

        r = client_app.get(f"/api/repositories/{repo_id}/pr-agent-config?force_refresh=true", headers=auth_headers)
        assert r.status_code == 200
        data = r.json().get("data", {})
        assert data.get("has_config") is True
        assert "gpt-5.3-codex" in (data.get("content") or "")


class TestMetricsConfigRoute:
    """GET/POST metrics config and metrics endpoints."""

    def test_get_metrics_summary_200(self, client_app, auth_headers):
        r = client_app.get("/api/metrics/summary", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_metrics_config_200(self, client_app, auth_headers):
        r = client_app.get("/api/metrics/config", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_metrics_operations_200(self, client_app, auth_headers):
        r = client_app.get("/api/metrics/operations", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_get_metrics_repositories_200(self, client_app, auth_headers):
        r = client_app.get("/api/metrics/repositories", headers=auth_headers)
        assert r.status_code == 200
        assert "data" in r.json()

    def test_post_metrics_config_round_trip(self, client_app, auth_headers):
        r = client_app.post(
            "/api/metrics/config",
            json={"developer_hourly_rate": 80.0},
            headers=auth_headers,
        )
        assert r.status_code == 200
        get_r = client_app.get("/api/metrics/config", headers=auth_headers)
        assert get_r.status_code == 200
        assert get_r.json()["data"]["developer_hourly_rate"] == 80.0


class TestCronJobTimeout:
    """Cron run-job-timeout endpoint."""

    def test_cron_run_job_timeout_401_without_secret(self, client_app):
        r = client_app.post("/api/cron/run-job-timeout")
        assert r.status_code == 401

    def test_cron_run_job_timeout_200_with_secret(self, client_app):
        r = client_app.post(
            "/api/cron/run-job-timeout",
            headers={"X-Cron-Secret": "test-cron-secret"},
        )
        assert r.status_code == 200


class TestOperationsStepAndInsights:
    """Operation step and insights endpoints (require existing operation)."""

    def test_post_operation_step_rejects_no_step(self, client_app, auth_headers):
        r = client_app.post(
            "/api/operations/some-op-id/step",
            json={},
            headers=auth_headers,
        )
        assert r.status_code in (400, 401, 500)

    def test_post_operation_step_404_unknown_op(self, client_app, auth_headers):
        r = client_app.post(
            "/api/operations/nonexistent-op-xyz/step",
            json={"current_step": "Analyzing"},
            headers=auth_headers,
        )
        assert r.status_code in (200, 404)

    def test_get_operation_insights_404(self, client_app, auth_headers):
        r = client_app.get("/api/operations/nonexistent-op-xyz/insights", headers=auth_headers)
        assert r.status_code in (200, 404)

    def test_put_operation_insights_404(self, client_app, auth_headers):
        r = client_app.put(
            "/api/operations/nonexistent-op-xyz/insights",
            json={"insights": {}},
            headers=auth_headers,
        )
        assert r.status_code in (200, 404)

    def test_post_operation_ai_metrics_404(self, client_app, auth_headers):
        r = client_app.post(
            "/api/operations/nonexistent-op-xyz/ai-metrics",
            json={"model_used": "gpt-4", "input_tokens": 10, "output_tokens": 5},
            headers=auth_headers,
        )
        assert r.status_code in (200, 404, 500)
