"""
Unit tests for SystemSettingsService (get/set/delete settings, pr-agent path, validation).
"""
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import database_manager
from services.system_settings_service import SystemSettingsService


@pytest.fixture
def ensure_system_settings_table():
    """Ensure system_settings table exists (same in-memory DB as app)."""
    database_manager.set_system_setting("_test_init", "_")
    yield
    try:
        svc = SystemSettingsService()
        svc.delete_setting("_test_init")
    except Exception:
        pass


@pytest.fixture
def service(ensure_system_settings_table):
    return SystemSettingsService()


class TestSystemSettingsServiceCRUD:
    """get_setting, set_setting, delete_setting, get_all_settings."""

    def test_set_and_get_setting(self, service):
        service.set_setting("test_key_abc", "value_123")
        assert service.get_setting("test_key_abc") == "value_123"

    def test_get_setting_missing_returns_none(self, service):
        assert service.get_setting("nonexistent_key_xyz") is None

    def test_delete_setting(self, service):
        service.set_setting("to_delete", "v")
        assert service.get_setting("to_delete") == "v"
        assert service.delete_setting("to_delete") is True
        assert service.get_setting("to_delete") is None

    def test_get_all_settings(self, service):
        service.set_setting("k1", "v1")
        service.set_setting("k2", "v2")
        all_ = service.get_all_settings()
        assert isinstance(all_, dict)
        assert all_.get("k1") == "v1"
        assert all_.get("k2") == "v2"


class TestSystemSettingsServicePrAgentPath:
    """PR-Agent path get/set and validation."""

    def test_get_set_pr_agent_install_path(self, service):
        service.set_pr_agent_install_path("/custom/path")
        assert service.get_pr_agent_install_path() == "/custom/path"

    def test_get_default_pr_agent_path_returns_string(self, service):
        path = service.get_default_pr_agent_path()
        assert isinstance(path, str)
        assert len(path) > 0

    def test_get_effective_pr_agent_path_fallback(self, service):
        with patch("config.settings", MagicMock(pr_agent_path=None)):
            path = service.get_effective_pr_agent_path()
            assert isinstance(path, str)
        with patch("config.settings", MagicMock(pr_agent_path="")):
            path = service.get_effective_pr_agent_path()
            assert isinstance(path, str)

    def test_get_effective_pr_agent_path_from_settings(self, service):
        with patch("config.settings", MagicMock(pr_agent_path="/from/settings")):
            path = service.get_effective_pr_agent_path()
            assert path == "/from/settings"

    def test_validate_pr_agent_path_path_does_not_exist(self, service):
        result = service.validate_pr_agent_path("/nonexistent/path/xyz_12345")
        assert result["valid"] is False
        assert "exist" in result.get("error", "").lower() or "not found" in str(result.get("details", "")).lower()

    def test_validate_pr_agent_path_not_a_directory(self, service):
        # Use current file path (a file, not a directory)
        file_path = os.path.abspath(__file__)
        result = service.validate_pr_agent_path(file_path)
        assert result["valid"] is False
        assert "directory" in result.get("error", "").lower() or "directory" in str(result.get("details", ""))

    def test_validate_pr_agent_path_settings_dir_missing(self, service):
        with tempfile.TemporaryDirectory() as tmp:
            result = service.validate_pr_agent_path(tmp)
        assert result["valid"] is False
        assert "settings" in result.get("error", "").lower() or "settings" in str(result.get("details", ""))

    def test_validate_pr_agent_path_config_file_missing(self, service):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pr_agent" / "settings").mkdir(parents=True)
            result = service.validate_pr_agent_path(tmp)
        assert result["valid"] is False
        assert "configuration" in result.get("error", "").lower() or "configuration" in str(result.get("details", ""))

    def test_validate_pr_agent_path_valid_with_three_files(self, service):
        with tempfile.TemporaryDirectory() as tmp:
            settings_dir = Path(tmp) / "pr_agent" / "settings"
            settings_dir.mkdir(parents=True)
            (settings_dir / "configuration.toml").write_text("[config]")
            (settings_dir / "ignore.toml").write_text("")
            (settings_dir / "language_extensions.toml").write_text("")
            (settings_dir / "pr_reviewer_prompts.toml").write_text("")
            result = service.validate_pr_agent_path(tmp)
        assert result["valid"] is True
        assert "details" in result and "found_files" in result["details"]

    def test_validate_pr_agent_path_validation_error_exception(self, service):
        with patch("services.system_settings_service.Path", side_effect=RuntimeError("bad")):
            result = service.validate_pr_agent_path("/any")
        assert result["valid"] is False
        assert result.get("error") == "Validation error"
        assert "bad" in str(result.get("details", ""))
