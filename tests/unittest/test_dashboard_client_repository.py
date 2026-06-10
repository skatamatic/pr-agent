"""
Unit tests for DashboardClient operation payloads (repository field contract).
No HTTP — mock _make_request only.
"""
import pytest

from pr_agent.log.dashboard_client import DashboardClient


@pytest.mark.asyncio
class TestDashboardClientRepositoryPayload:
    async def test_create_operation_json_uses_repository_key(self):
        client = DashboardClient(dashboard_url="http://dashboard.test")
        client._enabled = True

        captured = {}

        async def capture_make_request(method, endpoint, data=None):
            captured["method"] = method
            captured["endpoint"] = endpoint
            captured["data"] = data.copy() if data else {}
            return {"data": {"operation_id": "op-1"}}

        client._make_request = capture_make_request

        await client.create_operation(
            job_id="job-1",
            operation_type="review",
            command="review",
            repository="owner/repo-name",
            pr_url="https://example.com/pr/1",
        )

        assert captured["data"].get("repository") == "owner/repo-name"
        assert "repo" not in captured["data"]

    async def test_send_log_forwards_repository_payload(self):
        client = DashboardClient(dashboard_url="http://dashboard.test")
        client._enabled = True

        captured = {}

        async def capture_make_request(method, endpoint, data=None):
            captured["endpoint"] = endpoint
            captured["data"] = data.copy() if data else {}
            return {"status": "received"}

        client._make_request = capture_make_request

        await client.send_log(
            {
                "level": "INFO",
                "message": "hello",
                "repository": "org/app",
                "job_id": "j-1",
            }
        )

        assert captured["endpoint"] == "/logs/immediate"
        assert captured["data"].get("repository") == "org/app"
        assert "repo" not in captured["data"]

    async def test_send_logs_batch_wraps_logs_array(self):
        client = DashboardClient(dashboard_url="http://dashboard.test")
        client._enabled = True

        captured = {}

        async def capture_make_request(method, endpoint, data=None):
            captured["endpoint"] = endpoint
            captured["data"] = data
            return {"status": "received"}

        client._make_request = capture_make_request

        logs = [
            {"level": "INFO", "message": "a", "repository": "r1"},
            {"level": "WARN", "message": "b", "repository": "r2"},
        ]
        await client.send_logs_batch(logs)

        assert captured["endpoint"] == "/logs/batch"
        assert captured["data"]["logs"] == logs
