"""
Tests for cron API endpoints (Cloud Scheduler).
Requires DASHBOARD_CRON_SECRET; tests auth and skip behavior.
"""
import pytest
from unittest.mock import patch


class TestCronAPI:
    """Cron endpoints for run-cleanup and run-job-timeout."""

    def test_cron_run_cleanup_unauthorized_without_header(self, client_app):
        response = client_app.post("/api/cron/run-cleanup")
        assert response.status_code in (401, 503)
        # If secret not configured: 503; if configured and missing header: 401
        data = response.json()
        assert "detail" in data

    def test_cron_run_cleanup_unauthorized_with_wrong_secret(self, client_app):
        response = client_app.post(
            "/api/cron/run-cleanup",
            headers={"X-Cron-Secret": "wrong-secret"},
        )
        assert response.status_code == 401
        assert "Unauthorized" in response.json().get("detail", "")

    def test_cron_run_cleanup_success_with_correct_secret(self, client_app):
        import os
        secret = os.environ.get("DASHBOARD_CRON_SECRET", "test-cron-secret")
        response = client_app.post(
            "/api/cron/run-cleanup",
            headers={"X-Cron-Secret": secret},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        # With SQLite in-memory we get cleanup result; with non-SQLite we get skipped
        assert "message" in data

    def test_cron_run_cleanup_accepts_bearer_token(self, client_app):
        import os
        secret = os.environ.get("DASHBOARD_CRON_SECRET", "test-cron-secret")
        response = client_app.post(
            "/api/cron/run-cleanup",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert response.status_code == 200

    def test_cron_run_job_timeout_unauthorized_with_wrong_secret(self, client_app):
        response = client_app.post(
            "/api/cron/run-job-timeout",
            headers={"X-Cron-Secret": "wrong-secret"},
        )
        assert response.status_code == 401

    def test_cron_run_job_timeout_success_with_correct_secret(self, client_app):
        import os
        secret = os.environ.get("DASHBOARD_CRON_SECRET", "test-cron-secret")
        response = client_app.post(
            "/api/cron/run-job-timeout",
            headers={"X-Cron-Secret": secret},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "stale_marked_failed" in data["data"]
        assert "stale_found" in data["data"]
