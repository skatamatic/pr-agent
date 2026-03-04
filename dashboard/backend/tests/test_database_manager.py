"""
Tests for DatabaseManager system settings (get_system_setting, set_system_setting).
Uses the same in-memory DB as the app (conftest sets DATABASE_URL before imports).
"""
import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import database_manager


class TestDatabaseManagerSystemSettings:
    """DatabaseManager get_system_setting / set_system_setting (SQLite path)."""

    def test_set_and_get_system_setting(self):
        key = "test_setting_key_xyz"
        value = "test_value_123"
        success = database_manager.set_system_setting(key, value)
        assert success is True
        got = database_manager.get_system_setting(key)
        assert got == value

    def test_get_system_setting_missing_returns_none(self):
        got = database_manager.get_system_setting("nonexistent_key_xyz_999")
        assert got is None

    def test_set_system_setting_overwrite(self):
        key = "test_overwrite_key"
        database_manager.set_system_setting(key, "first")
        database_manager.set_system_setting(key, "second")
        assert database_manager.get_system_setting(key) == "second"
