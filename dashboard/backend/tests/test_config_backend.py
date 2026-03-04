"""
Tests for config backends: LocalConfigBackend backup and key handling.
"""
import pytest
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.config_backend import (
    LocalConfigBackend,
    CONFIG_KEY,
    BACKUP_PREFIX,
    MAX_BACKUPS,
)


@pytest.fixture
def temp_backend(tmp_path):
    """LocalConfigBackend backed by a temporary directory."""
    return LocalConfigBackend(Path(tmp_path))


class TestLocalConfigBackendBackups:
    """list_backup_ids, delete_backup, put_backup."""

    def test_list_backup_ids_empty(self, temp_backend):
        assert temp_backend.list_backup_ids() == []

    def test_put_backup_and_list(self, temp_backend):
        temp_backend.put_backup("2025-03-03T12-00-00", CONFIG_KEY, "[config]\nmodel = 'x'")
        ids = temp_backend.list_backup_ids()
        assert ids == ["2025-03-03T12-00-00"]

    def test_put_backup_content_restorable(self, temp_backend):
        content = "[config]\nmodel = 'test'"
        temp_backend.put_backup("2025-03-03T12-00-00", CONFIG_KEY, content)
        key = f"{BACKUP_PREFIX}2025-03-03T12-00-00/{CONFIG_KEY}"
        assert temp_backend.get(key) == content

    def test_list_backup_ids_sorted(self, temp_backend):
        temp_backend.put_backup("2025-03-04T00-00-00", CONFIG_KEY, "a")
        temp_backend.put_backup("2025-03-03T12-00-00", CONFIG_KEY, "b")
        ids = temp_backend.list_backup_ids()
        assert ids == ["2025-03-03T12-00-00", "2025-03-04T00-00-00"]

    def test_delete_backup_removes_dir(self, temp_backend):
        temp_backend.put_backup("2025-03-03T12-00-00", CONFIG_KEY, "x")
        assert len(temp_backend.list_backup_ids()) == 1
        temp_backend.delete_backup("2025-03-03T12-00-00")
        assert temp_backend.list_backup_ids() == []

    def test_delete_backup_nonexistent_no_error(self, temp_backend):
        temp_backend.delete_backup("nonexistent-id")

    @pytest.mark.parametrize("bad_id", ["../escape", "a/b", "", ".."])
    def test_put_backup_rejects_path_traversal(self, temp_backend, bad_id):
        temp_backend.put_backup(bad_id, CONFIG_KEY, "should not be stored")
        assert temp_backend.list_backup_ids() == []

    @pytest.mark.parametrize("bad_id", ["../escape", "a/b", "", ".."])
    def test_delete_backup_rejects_path_traversal(self, temp_backend, bad_id):
        temp_backend.put_backup("safe-id", CONFIG_KEY, "x")
        temp_backend.delete_backup(bad_id)
        assert temp_backend.list_backup_ids() == ["safe-id"]
