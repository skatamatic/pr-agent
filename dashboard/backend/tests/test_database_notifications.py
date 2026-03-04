"""
Tests for DatabaseManager notification methods: configs, events, update_event.
Uses in-memory DB; tables created by app startup.
"""
import pytest
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import database_manager, initialize_database


@pytest.fixture(scope="module")
def ensure_tables():
    initialize_database()
    yield


class TestDatabaseManagerNotificationConfigs:
    """get_notification_configs, save_notification_config, delete_notification_config."""

    def test_get_notification_configs_returns_list(self, ensure_tables):
        configs = database_manager.get_notification_configs()
        assert isinstance(configs, list)

    def test_save_notification_config_create(self, ensure_tables):
        config = database_manager.save_notification_config({
            "service_type": "teams",
            "name": "Test Teams",
            "enabled": True,
            "webhook_url": "https://outlook.com/x",
            "event_types": ["TEST"],
        })
        assert "id" in config
        assert config["service_type"] == "teams"
        assert config["name"] == "Test Teams"

    def test_save_notification_config_update(self, ensure_tables):
        configs = database_manager.get_notification_configs()
        if not configs:
            config = database_manager.save_notification_config({
                "service_type": "slack",
                "name": "Slack Test",
                "enabled": True,
                "event_types": [],
            })
            config_id = config["id"]
        else:
            config_id = configs[0]["id"]
        updated = database_manager.save_notification_config({
            "id": config_id,
            "name": "Updated Name",
            "enabled": False,
        })
        assert updated["id"] == config_id
        assert updated["name"] == "Updated Name"
        assert updated["enabled"] is False

    def test_delete_notification_config_nonexistent(self, ensure_tables):
        out = database_manager.delete_notification_config(999999)
        assert out is False


class TestDatabaseManagerNotificationEvents:
    """save_notification_event, get_notification_events, update_notification_event."""

    def test_save_notification_event_returns_id(self, ensure_tables):
        event = database_manager.save_notification_event({
            "event_type": "TEST",
            "event_data": {"message": "test"},
            "repositories": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        assert "id" in event
        assert event["event_type"] == "TEST"
        assert event["processed"] is False

    def test_get_notification_events_returns_list(self, ensure_tables):
        events = database_manager.get_notification_events(limit=5)
        assert isinstance(events, list)

    def test_get_notification_events_with_filter(self, ensure_tables):
        events = database_manager.get_notification_events(
            limit=5, event_type="TEST", offset=0
        )
        assert isinstance(events, list)

    def test_update_notification_event(self, ensure_tables):
        event = database_manager.save_notification_event({
            "event_type": "TEST",
            "event_data": {},
            "repositories": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        event_id = event["id"]
        ok = database_manager.update_notification_event(
            event_id,
            {"processed": True, "sent_to_services": ["teams"], "delivery_status": {"teams": "success"}},
        )
        assert ok is True

    def test_update_notification_event_nonexistent(self, ensure_tables):
        ok = database_manager.update_notification_event(999999, {"processed": True})
        assert ok is False

    def test_get_notification_events_count(self, ensure_tables):
        count = database_manager.get_notification_events_count()
        assert isinstance(count, int)
        count_type = database_manager.get_notification_events_count(event_type="TEST")
        assert isinstance(count_type, int)
