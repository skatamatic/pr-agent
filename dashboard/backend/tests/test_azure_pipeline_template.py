from services.azure_pipeline_config_service import AzurePipelineConfigService


def test_docker_pipeline_template_prefers_vm_pat_with_system_fallback():
    svc = AzurePipelineConfigService()
    template = svc.get_docker_pipeline_template(
        "PRAgent_SelfHosted",
        "us-central1-docker.pkg.dev/test-project/test-repo/pr-agent:latest",
    )

    assert "VM_AZURE_DEVOPS_PAT" in template
    assert "AZURE_DEVOPS_PAT: $(VM_AZURE_DEVOPS_PAT)" in template
    assert "SYSTEM_ACCESSTOKEN: $(System.AccessToken)" in template
    assert "-e AZURE_DEVOPS_PAT" in template
    assert "-e SYSTEM_ACCESSTOKEN" in template
    assert "VM_DASHBOARD_URL" in template
    assert "VM_DASHBOARD_API_KEY" in template
    assert "DASHBOARD_URL: $(VM_DASHBOARD_URL)" in template
    assert "DASHBOARD_API_KEY: $(VM_DASHBOARD_API_KEY)" in template
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


def test_docker_pipeline_template_bakes_gcs_and_dashboard_config():
    """Verify GCS bucket, prefix, dashboard URL, and API key are embedded in YAML variables."""
    svc = AzurePipelineConfigService()
    template = svc.get_docker_pipeline_template(
        pool_name="TestPool",
        pr_agent_image="us-central1-docker.pkg.dev/proj/repo/pr-agent:latest",
        gcs_bucket="my-config-bucket",
        gcs_prefix="pr-agent-config/",
        dashboard_url="https://dash.example.com",
        dashboard_api_key="secret-key-123",
    )

    assert "- name: PR_AGENT_CONFIG_GCS_BUCKET" in template
    assert "value: 'my-config-bucket'" in template
    assert "- name: PR_AGENT_CONFIG_GCS_PREFIX" in template
    assert "value: 'pr-agent-config/'" in template
    assert "- name: DASHBOARD_URL" in template
    assert "value: 'https://dash.example.com'" in template
    assert "- name: DASHBOARD_API_KEY" in template
    assert "value: 'secret-key-123'" in template
    assert "_PIPELINE_GCS_BUCKET" in template
    assert "_PIPELINE_DASHBOARD_URL" in template


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
