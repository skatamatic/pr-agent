import os
import sys
import pytest
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import RepositoryDB
from services.runner_health_service import RunnerHealthService


class _FakeResponse:
    def __init__(self, status: int, payload=None, text: str = "", reason: str = "OK"):
        self.status = status
        self._payload = payload if payload is not None else {}
        self._text = text
        self.reason = reason

    async def json(self):
        return self._payload

    async def text(self):
        return self._text


class _FakeRequestCtx:
    def __init__(self, response: _FakeResponse):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, headers=None):
        for needle, response in self.routes.items():
            if needle in url:
                return _FakeRequestCtx(response)
        return _FakeRequestCtx(_FakeResponse(404, payload={}, text="not found", reason="Not Found"))


def _make_repo(is_active: bool = True) -> RepositoryDB:
    return RepositoryDB(
        name="Product/TestRepo",
        provider="azure_devops",
        url="https://mdt-software.visualstudio.com/Product/_git/TestRepo",
        azure_pat="pat",
        is_active=is_active,
    )


@pytest.mark.asyncio
async def test_azure_health_warns_when_pr_agent_check_missing(monkeypatch):
    svc = RunnerHealthService()
    repo = _make_repo(is_active=True)

    fake_session = _FakeSession(
        {
            "/_apis/git/repositories/TestRepo": _FakeResponse(200, payload={"id": "repo1"}),
            "/_apis/distributedtask/pools?": _FakeResponse(200, payload={"value": [{"id": 1, "name": "Default"}]}),
            "/_apis/distributedtask/pools/1/agents": _FakeResponse(200, payload={"value": [{"status": "online"}]}),
        }
    )
    monkeypatch.setattr(svc, "_get_session", AsyncMock(return_value=fake_session))
    svc.azure_pipeline_config_service = type("FakeAzureService", (), {"list_build_policies": AsyncMock(return_value={"policies": []})})()

    result = await svc._check_azure_agent(repo)

    assert result["status"] == "warning"
    assert "check is missing" in (result.get("error") or "").lower()
    assert result.get("azure_repo_health", {}).get("repository_exists") is True
    assert result.get("azure_repo_health", {}).get("pr_agent_check_exists") is False


@pytest.mark.asyncio
async def test_azure_health_warns_when_active_check_disabled(monkeypatch):
    svc = RunnerHealthService()
    repo = _make_repo(is_active=True)

    fake_session = _FakeSession(
        {
            "/_apis/git/repositories/TestRepo": _FakeResponse(200, payload={"id": "repo1"}),
            "/_apis/distributedtask/pools?": _FakeResponse(200, payload={"value": [{"id": 1, "name": "Default"}]}),
            "/_apis/distributedtask/pools/1/agents": _FakeResponse(200, payload={"value": [{"status": "online"}]}),
        }
    )
    monkeypatch.setattr(svc, "_get_session", AsyncMock(return_value=fake_session))
    svc.azure_pipeline_config_service = type(
        "FakeAzureService",
        (),
        {
            "list_build_policies": AsyncMock(
                return_value={
                    "policies": [
                        {"policy_id": 1, "pipeline_name": "PR-Agent Review (main)", "is_enabled": False}
                    ]
                }
            )
        },
    )()

    result = await svc._check_azure_agent(repo)

    assert result["status"] == "warning"
    assert "active but pr-agent azure check is disabled" in (result.get("error") or "").lower()
    assert result.get("azure_repo_health", {}).get("active_check_enabled") is False


@pytest.mark.asyncio
async def test_azure_health_warns_when_repository_missing(monkeypatch):
    svc = RunnerHealthService()
    repo = _make_repo(is_active=True)

    fake_session = _FakeSession(
        {
            "/_apis/git/repositories/TestRepo": _FakeResponse(404, payload={}, reason="Not Found"),
            "/_apis/distributedtask/pools?": _FakeResponse(200, payload={"value": [{"id": 1, "name": "Default"}]}),
            "/_apis/distributedtask/pools/1/agents": _FakeResponse(200, payload={"value": [{"status": "online"}]}),
        }
    )
    monkeypatch.setattr(svc, "_get_session", AsyncMock(return_value=fake_session))
    svc.azure_pipeline_config_service = type("FakeAzureService", (), {"list_build_policies": AsyncMock(return_value={"policies": []})})()

    result = await svc._check_azure_agent(repo)

    assert result["status"] == "warning"
    assert "repository no longer exists" in (result.get("error") or "").lower()
    assert result.get("azure_repo_health", {}).get("repository_exists") is False
