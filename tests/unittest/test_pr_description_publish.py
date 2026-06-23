from unittest.mock import MagicMock, patch

from pr_agent.tools.pr_description import should_publish_pr_description


class TestShouldPublishPrDescription:
    @patch("pr_agent.tools.pr_description.get_settings")
    def test_requires_publish_output(self, mock_get_settings):
        settings = MagicMock()
        settings.config.publish_output = False
        settings.pr_description.get.return_value = True
        mock_get_settings.return_value = settings
        assert should_publish_pr_description() is False

    @patch("pr_agent.tools.pr_description.get_settings")
    def test_respects_publish_description_flag(self, mock_get_settings):
        settings = MagicMock()
        settings.config.publish_output = True
        settings.pr_description.get.return_value = False
        mock_get_settings.return_value = settings
        assert should_publish_pr_description() is False

    @patch("pr_agent.tools.pr_description.get_settings")
    def test_allows_publish_when_enabled(self, mock_get_settings):
        settings = MagicMock()
        settings.config.publish_output = True
        settings.pr_description.get.return_value = True
        mock_get_settings.return_value = settings
        assert should_publish_pr_description() is True
