"""
Tests for logs API: list, by job/operation, and log ingestion (immediate/batch).
Production-critical for PR Agent reporting and dashboard display.
"""
import pytest


class TestLogsAPI:
    """Logs read and ingestion endpoints."""

    def test_get_logs_returns_200_and_list(self, client_app, auth_headers):
        response = client_app.get("/api/logs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "logs" in data["data"]
        assert isinstance(data["data"]["logs"], list)

    def test_get_logs_with_limit(self, client_app, auth_headers):
        response = client_app.get("/api/logs?limit=10", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]["logs"]) <= 10

    def test_get_logs_by_job_returns_list(self, client_app, auth_headers):
        response = client_app.get("/api/logs/job/some-job-id", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data and "logs" in data["data"]

    def test_get_logs_by_operation_returns_list(self, client_app, auth_headers):
        response = client_app.get("/api/logs/operation/some-op-id", headers=auth_headers)
        assert response.status_code == 200
        assert "logs" in response.json()["data"]

    def test_post_logs_immediate_creates_log(self, client_app, auth_headers):
        payload = {
            "level": "INFO",
            "message": "Unique immediate log message for round-trip check",
            "source": "test",
        }
        response = client_app.post("/logs/immediate", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "received"
        assert "id" in data
        list_response = client_app.get("/api/logs?limit=50", headers=auth_headers)
        assert list_response.status_code == 200
        logs = list_response.json()["data"]["logs"]
        messages = [log.get("message") for log in logs if log.get("message")]
        assert "Unique immediate log message for round-trip check" in messages

    def test_post_logs_immediate_with_job_and_operation(self, client_app, auth_headers):
        payload = {
            "level": "INFO",
            "message": "Log with job and op",
            "job_id": "job-1",
            "operation_id": "op-1",
            "repository": "test/repo",
        }
        response = client_app.post("/logs/immediate", json=payload, headers=auth_headers)
        assert response.status_code == 200
        assert response.json().get("status") == "received"

    def test_post_logs_batch_accepts_empty_list(self, client_app, auth_headers):
        response = client_app.post("/logs/batch", json={"logs": []}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "received"
        assert data.get("count") == 0

    def test_post_logs_batch_creates_logs(self, client_app, auth_headers):
        payload = {
            "logs": [
                {"level": "INFO", "message": "Batch 1", "source": "test"},
                {"level": "INFO", "message": "Batch 2", "source": "test"},
            ]
        }
        response = client_app.post("/logs/batch", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "received"
        assert data.get("count") == 2

    def test_get_logs_with_level_param(self, client_app, auth_headers):
        client_app.post(
            "/logs/immediate",
            json={"level": "ERROR", "message": "Error-level log for filter test", "source": "test"},
            headers=auth_headers,
        )
        response = client_app.get("/api/logs?limit=20&level=INFO", headers=auth_headers)
        assert response.status_code == 200
        logs = response.json()["data"]["logs"]
        assert isinstance(logs, list)
        for log in logs:
            assert log.get("level") == "INFO"

    def test_get_logs_search_filters_message(self, client_app, auth_headers):
        needle = "unique-search-needle-xyz"
        client_app.post(
            "/logs/immediate",
            json={"level": "INFO", "message": needle, "source": "test"},
            headers=auth_headers,
        )
        r = client_app.get(f"/api/logs?search={needle}&limit=50", headers=auth_headers)
        assert r.status_code == 200
        logs = r.json()["data"]["logs"]
        assert all(needle in (log.get("message") or "") or needle.lower() in (log.get("message") or "").lower() for log in logs)

    def test_get_logs_offset_skips_rows(self, client_app, auth_headers):
        for i in range(3):
            client_app.post(
                "/logs/immediate",
                json={"level": "INFO", "message": f"offset-test-{i}", "source": "test"},
                headers=auth_headers,
            )
        r0 = client_app.get("/api/logs?limit=2&offset=0", headers=auth_headers)
        r1 = client_app.get("/api/logs?limit=2&offset=1", headers=auth_headers)
        assert r0.status_code == 200 and r1.status_code == 200
        ids0 = [x.get("id") for x in r0.json()["data"]["logs"]]
        ids1 = [x.get("id") for x in r1.json()["data"]["logs"]]
        if ids0 and ids1:
            assert ids0[0] != ids1[0]

    def test_get_logs_with_repo_param(self, client_app, auth_headers):
        # Use a unique repo so this test is not order-dependent on other tests' log data.
        unique_repo = "org/repo-filter-isolation-test"
        client_app.post(
            "/logs/immediate",
            json={
                "level": "INFO",
                "message": "repo filter isolation",
                "source": "test",
                "repository": unique_repo,
            },
            headers=auth_headers,
        )
        response = client_app.get(
            f"/api/logs?repo={unique_repo}&limit=20",
            headers=auth_headers,
        )
        assert response.status_code == 200
        logs = response.json()["data"]["logs"]
        assert isinstance(logs, list)
        assert logs, "expected at least one log when filtering by repo we just wrote"
        for log in logs:
            r = log.get("repo") or log.get("repository")
            assert r == unique_repo
