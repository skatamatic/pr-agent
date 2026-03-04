"""
Unit tests for GCP runner service: instance naming, config, and provision/deprovision with mocked client.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestGCPRunnerService:
    """GCPRunnerService behavior when GCP is configured and when client is mocked."""

    def test_safe_instance_name_sanitizes(self):
        from services.gcp_runner_service import _safe_instance_name
        assert _safe_instance_name("My-Org_123") == "my-org-123"
        assert _safe_instance_name("a" * 70) == "a" * 63
        assert _safe_instance_name("UPPER") == "upper"

    def test_is_configured_false_when_no_project(self):
        from services.gcp_runner_service import GCPRunnerService
        svc = GCPRunnerService(project_id="", region="us-central1", zone="us-central1-a")
        assert svc.is_configured() is False

    def test_is_configured_true_when_project_and_zone(self):
        from services.gcp_runner_service import GCPRunnerService
        svc = GCPRunnerService(project_id="my-project", region="us-central1", zone="us-central1-a")
        assert svc.is_configured() is True

    def test_instance_name_for_connection(self):
        from services.gcp_runner_service import GCPRunnerService
        svc = GCPRunnerService(project_id="p", region="us-central1", zone="us-central1-a", name_prefix="pr-agent-runner")
        name = svc.instance_name_for_connection(1, "github", "my-org", None)
        assert "pr-agent-runner" in name
        assert "1" in name
        assert "github" in name
        assert "my-org" in name
        assert len(name) <= 63
        name2 = svc.instance_name_for_connection(2, "azure_devops", "ado-org", "Proj")
        assert "2" in name2
        assert "proj" in name2 or "ado" in name2

    def test_provision_returns_error_when_not_configured(self):
        from services.gcp_runner_service import GCPRunnerService
        svc = GCPRunnerService(project_id="", region="us-central1")
        result = svc.provision(1, "github", "org", None)
        assert result["success"] is False
        assert "error" in result
        assert "configured" in result["error"].lower() or "GCP" in result["error"]

    def test_deprovision_returns_error_when_not_configured(self):
        from services.gcp_runner_service import GCPRunnerService
        svc = GCPRunnerService(project_id="", region="us-central1")
        result = svc.deprovision("some-instance", "us-central1-a")
        assert result["success"] is False
        assert "error" in result

    def test_deprovision_requires_instance_name_and_zone(self):
        from services.gcp_runner_service import GCPRunnerService
        svc = GCPRunnerService(project_id="p", region="us-central1", zone="us-central1-a")
        result = svc.deprovision("", "us-central1-a")
        assert result["success"] is False
        result2 = svc.deprovision("inst", "")
        assert result2["success"] is False

    def test_provision_with_mocked_client(self):
        from services.gcp_runner_service import GCPRunnerService, GCP_COMPUTE_AVAILABLE
        if not GCP_COMPUTE_AVAILABLE:
            pytest.skip("google-cloud-compute not installed")
        mock_op = Mock()
        mock_op.name = "op-123"
        mock_instances_client = Mock()
        mock_instances_client.insert.return_value = mock_op
        with patch("services.gcp_runner_service.compute_v1.InstancesClient", return_value=mock_instances_client):
            svc = GCPRunnerService(
                project_id="test-project",
                region="us-central1",
                zone="us-central1-a",
                dashboard_url="https://dashboard.example.com",
            )
            result = svc.provision(1, "github", "test-org", None)
        assert result["success"] is True
        assert result["instance_name"]
        assert result["zone"] == "us-central1-a"
        assert "install_instructions" in result
        assert result["install_instructions"].get("ssh_command")
        assert "github" in result["install_instructions"].get("docs_url", "").lower() or "runner" in str(result["install_instructions"])
