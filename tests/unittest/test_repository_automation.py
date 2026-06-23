from unittest.mock import MagicMock, patch

from pr_agent.algo.repository_automation import (
    _automation_env_overrides_active,
    _repo_settings_has_key,
    apply_dashboard_repository_automation,
)


class TestRepositoryAutomationHelpers:
    def test_repo_settings_has_key_detects_nested_values(self):
        repo_settings = {"azure_devops_config": {"auto_describe": False}}
        assert _repo_settings_has_key(repo_settings, "azure_devops_config", "auto_describe") is True
        assert _repo_settings_has_key(repo_settings, "azure_devops_config", "auto_review") is False

    @patch.dict("os.environ", {"AZURE_DEVOPS_CONFIG.AUTO_DESCRIBE": "true"}, clear=True)
    def test_automation_env_overrides_active(self):
        assert _automation_env_overrides_active() is True

    @patch("pr_agent.algo.repository_automation.DASHBOARD_AVAILABLE", False)
    def test_apply_dashboard_automation_noop_without_dashboard(self):
        apply_dashboard_repository_automation("https://github.com/o/r/pull/1", None)

    @patch("pr_agent.algo.repository_automation.asyncio.run")
    @patch("pr_agent.algo.repository_automation.extract_repository_from_url", return_value="org/repo")
    @patch("pr_agent.algo.repository_automation.DASHBOARD_AVAILABLE", True)
    @patch("pr_agent.algo.repository_automation._automation_env_overrides_active", return_value=False)
    def test_apply_dashboard_automation_sets_flags(self, _env_active, _extract, asyncio_run):
        asyncio_run.return_value = {
            "auto_describe": False,
            "auto_review": True,
            "auto_improve": False,
        }
        settings = MagicMock()
        with patch("pr_agent.algo.repository_automation.get_settings", return_value=settings):
            apply_dashboard_repository_automation("https://github.com/org/repo/pull/1", None)
            assert settings.set.call_count >= 4
