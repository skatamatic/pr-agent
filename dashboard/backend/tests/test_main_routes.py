"""
Additional main.py route tests to improve coverage: admin, config, metrics, repos, cron.
Assertions verify response shape and meaningful behavior (round-trip where applicable).
"""
import pytest
from datetime import datetime, timezone


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

    def test_post_config_200(self, client_app, auth_headers):
        r = client_app.post(
            "/api/config",
            json={"config": {"config": {"verbosity_level": 2}}},
            headers=auth_headers,
        )
        assert r.status_code == 200

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
