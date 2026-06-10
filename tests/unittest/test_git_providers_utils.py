"""Tests for pr_agent.git_providers.utils (config helpers)."""
from unittest.mock import MagicMock, patch

from pr_agent.git_providers.utils import (
    handle_configurations_errors,
    set_claude_model,
    _get_config_bool,
)


class TestGetConfigBool:
    def test_bool_passthrough(self):
        with patch("pr_agent.git_providers.utils.get_settings") as gs:
            gs.return_value.get.return_value = True
            assert _get_config_bool("use_repo_settings_file", False) is True

    def test_string_true(self):
        with patch("pr_agent.git_providers.utils.get_settings") as gs:
            gs.return_value.get.return_value = "  TRUE "
            assert _get_config_bool("use_repo_settings_file", False) is True

    def test_default_when_missing(self):
        with patch("pr_agent.git_providers.utils.get_settings") as gs:

            def getter(key, default=None):
                return default

            gs.return_value.get.side_effect = getter
            assert _get_config_bool("missing_key_xyz", False) is False


class TestSetClaudeModel:
    def test_sets_bedrock_model_ids(self):
        mock_settings = MagicMock()
        with patch("pr_agent.git_providers.utils.get_settings", return_value=mock_settings):
            set_claude_model()
        expected = "bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0"
        mock_settings.set.assert_any_call("config.model", expected)
        mock_settings.set.assert_any_call("config.model_weak", expected)
        mock_settings.set.assert_any_call("config.fallback_models", [expected])


class TestHandleConfigurationsErrors:
    def test_empty_list_noop(self):
        gp = MagicMock()
        handle_configurations_errors([], gp)
        gp.publish_comment.assert_not_called()
        gp.publish_persistent_comment.assert_not_called()

    def test_posts_persistent_comment_on_invalid_toml(self):
        gp = MagicMock()
        gp.is_supported.return_value = True
        err = {
            "error": "parse error",
            "settings": b'toml = [broken',
            "category": "local",
        }
        with patch("pr_agent.git_providers.utils.get_logger"):
            handle_configurations_errors([err], gp)
        gp.publish_persistent_comment.assert_called_once()
        call_kw = gp.publish_persistent_comment.call_args
        assert "parse error" in call_kw[0][0]

    def test_publish_comment_when_no_persistent_method(self):
        class GP:
            def __init__(self):
                self.comments = []

            def is_supported(self, name):
                return False

            def publish_comment(self, body):
                self.comments.append(body)

        gp = GP()
        err = {"error": "e", "settings": b"x = 1", "category": "local"}
        with patch("pr_agent.git_providers.utils.get_logger"):
            handle_configurations_errors([err], gp)
        assert len(gp.comments) == 1
