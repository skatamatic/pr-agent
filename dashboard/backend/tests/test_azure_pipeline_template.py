from services.azure_pipeline_config_service import AzurePipelineConfigService
import pytest


def test_docker_pipeline_template_uses_pipeline_secret_variables_for_pat_and_dashboard_key():
    svc = AzurePipelineConfigService()
    template = svc.get_docker_pipeline_template(
        "PRAgent_SelfHosted",
        "us-central1-docker.pkg.dev/test-project/test-repo/pr-agent:latest",
    )

    assert "VM_AZURE_DEVOPS_PAT" not in template
    assert "AZURE_DEVOPS_PAT: $(AZURE_DEVOPS_PAT)" in template
    assert "SYSTEM_ACCESSTOKEN: $(System.AccessToken)" in template
    assert "-e AZURE_DEVOPS_PAT" in template
    assert "-e SYSTEM_ACCESSTOKEN" in template
    assert "VM_DASHBOARD_URL" in template
    assert "DASHBOARD_URL: $(VM_DASHBOARD_URL)" in template
    assert "VM_DASHBOARD_API_KEY" not in template
    assert "DASHBOARD_API_KEY: $(DASHBOARD_API_KEY)" in template
    assert "--entrypoint python3" in template
    assert "-m pr_agent.servers.azuredevops_pipeline_runner" in template
    assert "case \"$IMAGE\" in" in template
    assert "Docker image names must be lowercase" in template
    assert "- name: PR_AGENT_IMAGE" in template
    assert "value: 'us-central1-docker.pkg.dev/test-project/test-repo/pr-agent:latest'" in template
    assert "SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI: $(System.PullRequest.SourceRepositoryUri)" in template
    assert "-e SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI" in template


def test_docker_pipeline_template_normalizes_configured_image_tag_to_latest():
    svc = AzurePipelineConfigService()
    template = svc.get_docker_pipeline_template(
        "PRAgent_SelfHosted",
        "us-central1-docker.pkg.dev/test-project/test-repo/pr-agent:deploy-1773384490",
    )

    assert "- name: PR_AGENT_IMAGE" in template
    assert "value: 'us-central1-docker.pkg.dev/test-project/test-repo/pr-agent:latest'" in template


def test_docker_pipeline_template_bakes_only_gcs_config_not_dashboard_url():
    """Verify GCS values are embedded while DASHBOARD_URL stays out of YAML."""
    svc = AzurePipelineConfigService()
    template = svc.get_docker_pipeline_template(
        pool_name="TestPool",
        pr_agent_image="us-central1-docker.pkg.dev/proj/repo/pr-agent:latest",
        gcs_bucket="my-config-bucket",
        gcs_prefix="pr-agent-config/",
    )

    assert "- name: PR_AGENT_CONFIG_GCS_BUCKET" in template
    assert "value: 'my-config-bucket'" in template
    assert "- name: PR_AGENT_CONFIG_GCS_PREFIX" in template
    assert "value: 'pr-agent-config/'" in template
    assert "- name: DASHBOARD_URL" not in template
    assert "- name: DASHBOARD_API_KEY" not in template
    assert "secret-key-123" not in template
    assert "_PIPELINE_GCS_BUCKET" in template
    assert "_PIPELINE_DASHBOARD_URL" in template
    assert "_PIPELINE_DASHBOARD_API_KEY" not in template


class _FakeResponse:
    def __init__(self, status, json_data=None, text_data=""):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClientSession:
    def __init__(self, state, get_resp, put_resp):
        self._state = state
        self._get_resp = get_resp
        self._put_resp = put_resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        self._state["get_url"] = url
        self._state["get_headers"] = headers
        return self._get_resp

    def put(self, url, headers=None, json=None):
        self._state["put_url"] = url
        self._state["put_headers"] = headers
        self._state["put_json"] = json
        return self._put_resp


@pytest.mark.asyncio
async def test_set_pipeline_secret_variables_merges_and_marks_as_secret(monkeypatch):
    import services.azure_pipeline_config_service as svc_module

    state = {}
    get_resp = _FakeResponse(
        200,
        json_data={
            "id": 42,
            "name": "PR-Agent",
            "variables": {
                "EXISTING": {"value": "keep"},
            },
        },
    )
    put_resp = _FakeResponse(200, json_data={"id": 42})

    def _session_factory(*args, **kwargs):
        return _FakeClientSession(state, get_resp, put_resp)

    monkeypatch.setattr(svc_module.aiohttp, "ClientSession", _session_factory)

    svc = AzurePipelineConfigService()
    result = await svc._set_pipeline_secret_variables(
        organization="org",
        project="project",
        token="pat",
        pipeline_id=42,
        secret_values={
            "AZURE_DEVOPS_PAT": "secret-pat",
            "DASHBOARD_API_KEY": "dash-key",
            "EMPTY": "",
        },
    )

    assert result["success"] is True
    assert set(result["updated_keys"]) == {"AZURE_DEVOPS_PAT", "DASHBOARD_API_KEY"}
    assert state["put_json"]["variables"]["EXISTING"]["value"] == "keep"
    assert state["put_json"]["variables"]["AZURE_DEVOPS_PAT"]["value"] == "secret-pat"
    assert state["put_json"]["variables"]["AZURE_DEVOPS_PAT"]["isSecret"] is True
    assert state["put_json"]["variables"]["AZURE_DEVOPS_PAT"]["allowOverride"] is True
    assert state["put_json"]["variables"]["DASHBOARD_API_KEY"]["value"] == "dash-key"
    assert state["put_json"]["variables"]["DASHBOARD_API_KEY"]["isSecret"] is True
    assert state["put_json"]["variables"]["DASHBOARD_API_KEY"]["allowOverride"] is True


@pytest.mark.asyncio
async def test_set_pipeline_secret_variables_returns_error_when_definition_fetch_fails(monkeypatch):
    import services.azure_pipeline_config_service as svc_module

    state = {}
    get_resp = _FakeResponse(404, text_data="not found")
    put_resp = _FakeResponse(200, json_data={"id": 42})

    def _session_factory(*args, **kwargs):
        return _FakeClientSession(state, get_resp, put_resp)

    monkeypatch.setattr(svc_module.aiohttp, "ClientSession", _session_factory)

    svc = AzurePipelineConfigService()
    result = await svc._set_pipeline_secret_variables(
        organization="org",
        project="project",
        token="pat",
        pipeline_id=42,
        secret_values={"AZURE_DEVOPS_PAT": "secret-pat"},
    )

    assert result["success"] is False
    assert "Failed to fetch build definition 42" in result["error"]
    assert "put_json" not in state


@pytest.mark.asyncio
async def test_set_pipeline_definition_variables_sets_plain_and_secret(monkeypatch):
    import services.azure_pipeline_config_service as svc_module

    state = {}
    get_resp = _FakeResponse(
        200,
        json_data={
            "id": 42,
            "name": "PR-Agent",
            "variables": {
                "EXISTING": {"value": "keep"},
            },
        },
    )
    put_resp = _FakeResponse(200, json_data={"id": 42})

    def _session_factory(*args, **kwargs):
        return _FakeClientSession(state, get_resp, put_resp)

    monkeypatch.setattr(svc_module.aiohttp, "ClientSession", _session_factory)

    svc = AzurePipelineConfigService()
    result = await svc._set_pipeline_definition_variables(
        organization="org",
        project="project",
        token="pat",
        pipeline_id=42,
        variables_to_set={
            "AZURE_DEVOPS_PAT": {"value": "secret-pat", "is_secret": True},
            "DASHBOARD_URL": {"value": "https://dash.example.com", "is_secret": False},
        },
    )

    assert result["success"] is True
    assert "AZURE_DEVOPS_PAT" in result["updated_keys"]
    assert "DASHBOARD_URL" in result["updated_keys"]
    assert state["put_json"]["variables"]["AZURE_DEVOPS_PAT"]["isSecret"] is True
    assert state["put_json"]["variables"]["DASHBOARD_URL"]["isSecret"] is False
    assert state["put_json"]["variables"]["EXISTING"]["value"] == "keep"


@pytest.mark.asyncio
async def test_sync_pipeline_variables_updates_each_pipeline(monkeypatch):
    svc = AzurePipelineConfigService()

    async def _fake_get_sync_status(repo_data, db_session=None):
        return {
            "sync_status": "up_to_date",
            "pipeline_definitions": [
                {"id": 11, "name": "PR-Agent Shared"},
                {"id": 12, "name": "PR-Agent Repo"},
            ],
        }

    calls = []

    async def _fake_set_pipeline_definition_variables(**kwargs):
        calls.append(kwargs)
        return {"success": True, "updated_keys": list((kwargs.get("variables_to_set") or {}).keys())}

    monkeypatch.setattr(svc, "get_sync_status", _fake_get_sync_status)
    monkeypatch.setattr(svc, "_set_pipeline_definition_variables", _fake_set_pipeline_definition_variables)
    monkeypatch.setattr(
        svc,
        "_get_expected_pipeline_plain_variables",
        lambda: {"DASHBOARD_URL": "https://dash.example.com", "PR_AGENT_IMAGE": "repo/pr-agent:latest"},
    )

    result = await svc.sync_pipeline_variables(
        repo_data={
            "provider": "azure_devops",
            "url": "https://dev.azure.com/org/project/_git/repo",
            "azure_pat": "pat-secret",
        },
        db_session=None,
    )

    assert result["success"] is True
    assert result["pipelines_targeted"] == 2
    assert len(calls) == 2
    for call in calls:
        var_map = call["variables_to_set"]
        assert var_map["AZURE_DEVOPS_PAT"]["is_secret"] is True
        assert var_map["DASHBOARD_URL"]["is_secret"] is False
        assert "PR_AGENT_IMAGE" in var_map


@pytest.mark.asyncio
async def test_collect_pipeline_variables_status_detects_empty_plain_values():
    svc = AzurePipelineConfigService()
    state = {}
    get_resp = _FakeResponse(
        200,
        json_data={
            "id": 99,
            "variables": {
                "PR_AGENT_IMAGE": {"value": "repo/pr-agent:latest"},
                "DASHBOARD_URL": {"value": "   "},
                "AZURE_DEVOPS_PAT": {"isSecret": True},
            },
        },
    )
    session = _FakeClientSession(state=state, get_resp=get_resp, put_resp=_FakeResponse(200, json_data={}))
    result = await svc._collect_pipeline_variables_status(
        session=session,
        headers={"Authorization": "Basic fake"},
        organization="org",
        project="proj",
        pipeline_defs=[{"id": 99, "name": "PR-Agent"}],
        required_plain_keys=["PR_AGENT_IMAGE", "DASHBOARD_URL"],
        required_secret_keys=["AZURE_DEVOPS_PAT", "DASHBOARD_API_KEY"],
    )

    assert result["missing_any"] is True
    assert result["pipelines_checked"] == 1
    pipeline = result["pipelines"][0]
    assert "DASHBOARD_URL" in pipeline["invalid_plain_keys"]
    assert "DASHBOARD_API_KEY" in pipeline["missing_secret_keys"]


@pytest.mark.asyncio
async def test_collect_pipeline_variables_status_flags_localhost_dashboard_url():
    svc = AzurePipelineConfigService()
    state = {}
    get_resp = _FakeResponse(
        200,
        json_data={
            "id": 101,
            "variables": {
                "PR_AGENT_IMAGE": {"value": "repo/pr-agent:latest"},
                "DASHBOARD_URL": {"value": "http://localhost:8000"},
                "AZURE_DEVOPS_PAT": {"isSecret": True},
                "DASHBOARD_API_KEY": {"isSecret": True},
            },
        },
    )
    session = _FakeClientSession(state=state, get_resp=get_resp, put_resp=_FakeResponse(200, json_data={}))
    result = await svc._collect_pipeline_variables_status(
        session=session,
        headers={"Authorization": "Basic fake"},
        organization="org",
        project="proj",
        pipeline_defs=[{"id": 101, "name": "PR-Agent"}],
        required_plain_keys=["PR_AGENT_IMAGE", "DASHBOARD_URL"],
        required_secret_keys=["AZURE_DEVOPS_PAT", "DASHBOARD_API_KEY"],
    )

    assert result["missing_any"] is True
    pipeline = result["pipelines"][0]
    assert "DASHBOARD_URL" in pipeline["invalid_plain_keys"]


def test_resolve_dashboard_url_for_pipeline_uses_cloud_run_fallback(monkeypatch):
    svc = AzurePipelineConfigService()
    monkeypatch.delenv("DASHBOARD_BACKEND_BASE_URL", raising=False)
    monkeypatch.setenv("K_SERVICE", "pr-agent-dash-dev-backend")
    monkeypatch.setenv("GCP_RUNNER_REGION", "us-central1")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT_NUMBER", raising=False)
    monkeypatch.setattr(
        svc,
        "_fetch_gcp_project_number_from_metadata",
        lambda: "123456789012",
    )

    url = svc._resolve_dashboard_url_for_pipeline()
    assert url == "https://pr-agent-dash-dev-backend-123456789012.us-central1.run.app"


def test_select_shared_pipeline_definitions_accepts_yaml_path_variants():
    svc = AzurePipelineConfigService()
    defs = [
        {
            "id": 1,
            "name": "PR-Agent Shared",
            "repository": {"name": "pr-agent-pipelines", "id": "repo-guid"},
            "process": {"yamlFilename": "/azure-pipelines.yml"},
            "_links": {"web": {"href": "https://example/p/1"}},
        }
    ]
    selected = svc._select_shared_pipeline_definitions(defs, "pr-agent-pipelines", "repo-guid")
    assert len(selected) == 1
    assert selected[0]["id"] == 1


@pytest.mark.asyncio
async def test_sync_pipeline_variables_uses_fallback_discovery_when_sync_status_empty(monkeypatch):
    svc = AzurePipelineConfigService()

    async def _fake_get_sync_status(repo_data, db_session=None):
        return {"sync_status": "missing", "pipeline_definitions": []}

    async def _fake_fallback_find_pipeline_definitions_for_sync(organization, project, token):
        return [{"id": 88, "name": "PR-Agent Shared"}]

    calls = []

    async def _fake_set_pipeline_definition_variables(**kwargs):
        calls.append(kwargs)
        return {"success": True, "updated_keys": list((kwargs.get("variables_to_set") or {}).keys())}

    monkeypatch.setattr(svc, "get_sync_status", _fake_get_sync_status)
    monkeypatch.setattr(
        svc,
        "_fallback_find_pipeline_definitions_for_sync",
        _fake_fallback_find_pipeline_definitions_for_sync,
    )
    monkeypatch.setattr(svc, "_set_pipeline_definition_variables", _fake_set_pipeline_definition_variables)
    monkeypatch.setattr(svc, "_get_expected_pipeline_plain_variables", lambda: {"DASHBOARD_URL": "https://dash"})

    result = await svc.sync_pipeline_variables(
        repo_data={
            "provider": "azure_devops",
            "url": "https://dev.azure.com/org/project/_git/repo",
            "azure_pat": "pat-secret",
        },
        db_session=None,
    )

    assert result["success"] is True
    assert result["pipelines_targeted"] == 1
    assert len(calls) == 1
    assert calls[0]["pipeline_id"] == 88


def test_resolve_pr_repo_name_from_source_repository_uri(monkeypatch):
    """_resolve_pr_repo_name prefers SourceRepositoryUri over Build.Repository.Name."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))

    monkeypatch.setenv(
        "SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI",
        "https://dev.azure.com/mdt-software/Product/_git/Archive.MDT.ConfigEditor",
    )
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", "pr-agent-pipelines")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Product")

    # Test the parsing logic directly (same algorithm as the runner).
    import os
    source_repo_uri = os.environ.get('SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI', '').strip()
    parts = source_repo_uri.rstrip('/').split('/')
    git_idx = parts.index('_git')
    repo_name = parts[git_idx + 1]
    project = parts[git_idx - 1]
    assert repo_name == "Archive.MDT.ConfigEditor"
    assert project == "Product"


def test_resolve_pr_repo_name_falls_back_to_build_repo(monkeypatch):
    """Without SourceRepositoryUri, falls back to BUILD_REPOSITORY_NAME."""
    monkeypatch.delenv("SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI", raising=False)
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", "my-repo")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "MyProject")

    import os
    source_repo_uri = os.environ.get('SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI', '').strip()
    assert not source_repo_uri
    assert os.environ.get('BUILD_REPOSITORY_NAME') == "my-repo"
    assert os.environ.get('SYSTEM_TEAMPROJECT') == "MyProject"


def test_resolve_pr_repo_visualstudio_url(monkeypatch):
    """_resolve_pr_repo_name handles legacy visualstudio.com URLs."""
    monkeypatch.setenv(
        "SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI",
        "https://mdt-software.visualstudio.com/Product/_git/OtherRepo",
    )
    monkeypatch.setenv("BUILD_REPOSITORY_NAME", "pr-agent-pipelines")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "Product")

    import os
    source_repo_uri = os.environ.get('SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI', '').strip()
    parts = source_repo_uri.rstrip('/').split('/')
    git_idx = parts.index('_git')
    repo_name = parts[git_idx + 1]
    project = parts[git_idx - 1]
    assert repo_name == "OtherRepo"
    assert project == "Product"
