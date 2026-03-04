"""
Tests for RetentionService: SQLite vs non-SQLite (Cloud SQL) paths.
"""
import pytest
from unittest.mock import Mock, patch
import os
import tempfile

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.retention_service import RetentionService


def _make_mock_db_manager():
    """Mock database_manager that returns safe values for RetentionService __init__."""
    m = Mock()
    backup_dir = os.path.join(tempfile.gettempdir(), "dashboard_backups_test")
    m.get_system_setting = Mock(side_effect=lambda k: backup_dir if k == "backup_directory" else None)
    return m


class TestRetentionServiceNonSQLite:
    """When DATABASE_URL is PostgreSQL, cleanup/backup/restore return clear messages."""

    def test_perform_cleanup_returns_skip_when_not_sqlite(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@host/db"}, clear=False):
            svc = RetentionService(mock_db_manager)
        assert svc._use_sqlite is False
        result = svc.perform_cleanup(dry_run=False)
        assert result.get("total_deleted") == 0
        assert "errors" in result
        assert any("Cloud SQL" in e or "SQLite" in e for e in result["errors"])

    def test_create_backup_returns_error_when_not_sqlite(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@host/db"}, clear=False):
            svc = RetentionService(mock_db_manager)
        result = svc.create_backup()
        assert result.get("success") is False
        assert "Cloud SQL" in result.get("error", "") or "not available" in result.get("error", "").lower()


class TestRetentionServiceSQLite:
    """Retention config and structure when service is initialized."""

    def test_get_retention_config_returns_dict(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        config = svc.get_retention_config()
        assert isinstance(config, dict)
        assert "log_retention_days" in config or "job_retention_days" in config

    def test_update_retention_config_returns_true(self):
        mock_db_manager = _make_mock_db_manager()
        mock_db_manager.set_system_setting = Mock(return_value=True)
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        ok = svc.update_retention_config({"log_retention_days": 14, "job_retention_days": 60})
        assert ok is True
        mock_db_manager.set_system_setting.assert_called()

    def test_get_database_stats_returns_dict(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        stats = svc.get_database_stats()
        assert isinstance(stats, dict)
        assert "jobs_count" in stats or "size_mb" in stats or "table_stats" in stats

    def test_get_backup_list_returns_list(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        backups = svc.get_backup_list()
        assert isinstance(backups, list)

    def test_create_backup_sqlite_success(self):
        mock_db_manager = _make_mock_db_manager()
        backup_dir = os.path.join(tempfile.gettempdir(), "dashboard_retention_test_backup")
        mock_db_manager.get_system_setting = Mock(
            side_effect=lambda k: backup_dir if k == "backup_directory" else None
        )
        os.makedirs(backup_dir, exist_ok=True)
        try:
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
                svc = RetentionService(mock_db_manager)
            result = svc.create_backup(compressed=True)
            assert result.get("success") is True
            assert "filename" in result or "file_path" in result
        finally:
            import shutil
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)

    def test_perform_cleanup_sqlite_dry_run(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        result = svc.perform_cleanup(dry_run=True)
        assert isinstance(result, dict)
        assert "total_deleted" in result or "errors" in result

    def test_should_perform_automatic_backup(self):
        mock_db_manager = _make_mock_db_manager()
        mock_db_manager.get_system_setting = Mock(return_value=None)
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        out = svc.should_perform_automatic_backup()
        assert isinstance(out, bool)

    def test__validate_config(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        validated = svc._validate_config({
            "log_retention_days": 7,
            "cleanup_strategy": "time",
            "auto_backup_enabled": False,
        })
        assert validated["log_retention_days"] == 7
        assert validated["cleanup_strategy"] == "time"
        assert validated["auto_backup_enabled"] is False

    def test_perform_cleanup_sqlite_execute(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        result = svc.perform_cleanup(dry_run=False)
        assert isinstance(result, dict)
        assert "total_deleted" in result or "errors" in result

    def test_export_data_csv_returns_content(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        result = svc.export_data(format="csv")
        assert result.get("success") is True
        assert "content" in result
        assert result.get("content_type") == "text/csv"

    def test_export_data_unsupported_format(self):
        mock_db_manager = _make_mock_db_manager()
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///:memory:"}, clear=False):
            svc = RetentionService(mock_db_manager)
        result = svc.export_data(format="xml")
        assert result.get("success") is False
        assert "Unsupported" in result.get("error", "")
