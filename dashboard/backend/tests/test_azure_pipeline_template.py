from services.azure_pipeline_config_service import AzurePipelineConfigService


def test_docker_pipeline_template_prefers_vm_pat_with_system_fallback():
    svc = AzurePipelineConfigService()
    template = svc.get_docker_pipeline_template("PRAgent_SelfHosted")

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
