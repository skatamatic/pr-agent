"""
Tests for operations and jobs list/get API.
Uses in-memory DB; some endpoints require auth (JWT or DASHBOARD_API_KEY).
"""
import pytest
from unittest.mock import patch


class TestOperationsJobsAPI:
    """Operations and jobs read endpoints."""

    def test_get_jobs_requires_auth(self, client_app):
        response = client_app.get("/api/jobs")
        assert response.status_code == 401

    def test_get_jobs_returns_200_and_list(self, client_app, auth_headers):
        response = client_app.get("/api/jobs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "total" in data

    def test_get_jobs_with_limit(self, client_app, auth_headers):
        response = client_app.get("/api/jobs?limit=5", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) <= 5

    def test_get_job_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.get("/api/jobs/nonexistent-job-id-12345", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_get_operations_requires_auth(self, client_app):
        response = client_app.get("/api/operations")
        assert response.status_code == 401

    def test_get_operations_with_token_returns_list(self, client_app):
        login = client_app.post(
            "/api/auth/login",
            json={"username": "admin", "password": "mobile"},
        )
        token = login.json()["data"]["token"]
        response = client_app.get(
            "/api/operations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "operations" in data["data"]
        assert isinstance(data["data"]["operations"], list)

    def test_get_operation_not_found_returns_404(self, client_app, auth_headers):
        response = client_app.get("/api/operations/nonexistent-op-id-12345", headers=auth_headers)
        assert response.status_code == 404

    def test_get_job_operations_returns_list(self, client_app, auth_headers):
        # First get any job id from list, or use a fake one
        list_resp = client_app.get("/api/jobs?limit=1", headers=auth_headers)
        assert list_resp.status_code == 200
        jobs = list_resp.json().get("data") or []
        if jobs:
            job_id = jobs[0].get("job_id") or jobs[0].get("id")
            response = client_app.get(f"/api/jobs/{job_id}/operations", headers=auth_headers)
            assert response.status_code == 200
            assert "data" in response.json()
            assert "operations" in response.json()["data"]
        else:
            response = client_app.get("/api/jobs/fake-job-id/operations", headers=auth_headers)
            assert response.status_code in (200, 404)
            if response.status_code == 200:
                assert response.json().get("data", {}).get("operations") == []

    def test_post_jobs_create_without_auth_returns_401(self, client_app):
        response = client_app.post(
            "/api/jobs/create",
            json={"repository": "test/repo", "job_type": "manual", "source": "test"},
        )
        assert response.status_code == 401

    def test_post_jobs_create_with_api_key_returns_200(self, client_app):
        import main
        # Set API key so dashboard accepts Bearer test-api-key; restore after (dynaconf doesn't support delattr)
        old_key = getattr(main.settings, "dashboard_api_key", "")
        setattr(main.settings, "dashboard_api_key", "test-api-key")
        try:
            response = client_app.post(
                "/api/jobs/create",
                json={"repository": "test/repo", "job_type": "manual", "source": "test"},
                headers={"Authorization": "Bearer test-api-key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "data" in data and "job_id" in data["data"]
        finally:
            setattr(main.settings, "dashboard_api_key", old_key)

    def test_post_jobs_create_returns_200_and_job_id(self, client_app, auth_headers):
        response = client_app.post(
            "/api/jobs/create",
            json={"repository": "test/repo", "job_type": "manual", "source": "test"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data and "job_id" in data["data"]
        assert data["data"]["job_id"]

    def test_post_jobs_create_with_job_id_returns_200(self, client_app, auth_headers):
        response = client_app.post(
            "/api/jobs/create",
            json={
                "job_id": "test-job-create-123",
                "repository": "test/repo",
                "job_type": "manual",
                "source": "test",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["job_id"] == "test-job-create-123"

    def test_post_job_status_returns_200(self, client_app, auth_headers):
        create = client_app.post(
            "/api/jobs/create",
            json={"repository": "r", "job_type": "manual", "source": "test"},
            headers=auth_headers,
        )
        assert create.status_code == 200
        job_id = create.json()["data"]["job_id"]
        response = client_app.post(
            f"/api/jobs/{job_id}/status",
            json={"status": "completed", "completed_at": "2024-01-15T12:00:00Z"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        get_job = client_app.get(f"/api/jobs/{job_id}", headers=auth_headers)
        assert get_job.status_code == 200
        assert get_job.json()["data"].get("status") == "completed"

    def test_post_operations_create_returns_200(self, client_app, auth_headers):
        create_job = client_app.post(
            "/api/jobs/create",
            json={"repository": "r", "job_type": "manual", "source": "test"},
            headers=auth_headers,
        )
        assert create_job.status_code == 200
        job_id = create_job.json()["data"]["job_id"]
        response = client_app.post(
            "/api/operations/create",
            json={"job_id": job_id, "operation_type": "review", "repository": "r"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data and "operation_id" in data["data"]

    def test_post_operation_status_returns_200(self, client_app, auth_headers):
        create_job = client_app.post(
            "/api/jobs/create",
            json={"repository": "r", "job_type": "manual", "source": "test"},
            headers=auth_headers,
        )
        assert create_job.status_code == 200
        job_id = create_job.json()["data"]["job_id"]
        create_op = client_app.post(
            "/api/operations/create",
            json={"job_id": job_id, "operation_type": "review", "repository": "r"},
            headers=auth_headers,
        )
        assert create_op.status_code == 200
        op_id = create_op.json()["data"]["operation_id"]
        response = client_app.post(
            f"/api/operations/{op_id}/status",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        get_op = client_app.get(f"/api/operations/{op_id}", headers=auth_headers)
        assert get_op.status_code == 200
        assert get_op.json()["data"].get("status") == "completed"

    def test_get_job_deletion_preview_nonexistent_returns_404(self, client_app, auth_headers):
        response = client_app.get("/api/jobs/nonexistent-job-id-xyz/deletion-preview", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_job_nonexistent_returns_404(self, client_app, auth_headers):
        response = client_app.delete("/api/jobs/nonexistent-job-id-99999", headers=auth_headers)
        assert response.status_code == 404
