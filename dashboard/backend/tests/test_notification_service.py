"""
Unit tests for NotificationService (load_config, _should_send, _get_event_details, send_notification).
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.notification_service import NotificationService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_notification_configs.return_value = []
    db.save_notification_event.return_value = {"id": 1}
    db.update_notification_event.return_value = None
    return db


@pytest.fixture
def service(mock_db):
    return NotificationService(mock_db)


class TestNotificationServiceLoadConfig:
    def test_load_configurations_empty(self, mock_db):
        mock_db.get_notification_configs.return_value = []
        svc = NotificationService(mock_db)
        assert svc.enabled_services == {}

    def test_load_configurations_enabled_only(self, mock_db):
        mock_db.get_notification_configs.return_value = [
            {"service_type": "TEAMS", "enabled": True, "webhook_url": "https://x"},
            {"service_type": "SLACK", "enabled": False},
        ]
        svc = NotificationService(mock_db)
        assert "TEAMS" in svc.enabled_services
        assert "SLACK" not in svc.enabled_services

    def test_load_configurations_exception(self, mock_db):
        mock_db.get_notification_configs.side_effect = RuntimeError("db error")
        svc = NotificationService(mock_db)
        assert svc.enabled_services == {}


class TestShouldSendNotification:
    def test_test_event_always_sent(self, service):
        assert service._should_send_notification({}, "TEST", []) is True

    def test_event_type_not_in_config(self, service):
        config = {"event_types": ["JOB_SUCCESS"]}
        assert service._should_send_notification(config, "NEW_JOB", []) is False

    def test_event_type_in_config_no_repo_filter(self, service):
        config = {"event_types": ["NEW_JOB"]}
        assert service._should_send_notification(config, "NEW_JOB", ["repo/a"]) is True

    def test_repo_filter_match(self, service):
        config = {"event_types": ["NEW_JOB"], "repository_filter": ["repo/a"]}
        assert service._should_send_notification(config, "NEW_JOB", ["repo/a"]) is True

    def test_repo_filter_no_match(self, service):
        config = {"event_types": ["NEW_JOB"], "repository_filter": ["repo/b"]}
        assert service._should_send_notification(config, "NEW_JOB", ["repo/a"]) is False


class TestGetEventDetails:
    def test_new_job(self, service):
        event = {
            "event_type": "NEW_JOB",
            "event_data": {"job_type": "review", "repository": "org/repo", "trigger_user": "alice"},
        }
        title, color, summary = service._get_event_details(event)
        assert "New" in title and "Job" in title
        assert color == "#4CAF50"
        assert "alice" in summary and "org/repo" in summary

    def test_job_success(self, service):
        event = {
            "event_type": "JOB_SUCCESS",
            "event_data": {"job_type": "review", "repository": "org/repo", "duration": 120},
        }
        title, color, summary = service._get_event_details(event)
        assert "Completed" in title
        assert "2m" in summary or "120" in summary

    def test_job_failure(self, service):
        event = {
            "event_type": "JOB_FAILURE",
            "event_data": {"repository": "org/repo", "error_details": "timeout"},
        }
        title, color, summary = service._get_event_details(event)
        assert "Failed" in title
        assert color == "#F44336"
        assert "timeout" in summary

    def test_test_notification(self, service):
        event = {
            "event_type": "TEST",
            "event_data": {"service_type": "teams", "message": "hello"},
        }
        title, color, summary = service._get_event_details(event)
        assert "Test" in title
        assert summary == "hello"

    def test_unknown_event_type(self, service):
        event = {"event_type": "UNKNOWN_TYPE", "event_data": {}}
        title, color, summary = service._get_event_details(event)
        assert "Unknown" in title or "unknown" in summary.lower()
        assert color == "#9E9E9E"


class TestFormatDuration:
    def test_format_duration_seconds(self, service):
        assert "5s" in service._format_duration(5) or "5" in service._format_duration(5)

    def test_format_duration_minutes(self, service):
        out = service._format_duration(125)
        assert "2" in out and "5" in out

    def test_format_duration_none(self, service):
        assert "unknown" in service._format_duration(None).lower()


class TestSendNotification:
    @pytest.mark.asyncio
    async def test_send_no_enabled_services_returns_false(self, service):
        result = await service.send_notification("NEW_JOB", {"repository": "r"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_with_teams_mock_success(self, mock_db):
        mock_db.get_notification_configs.return_value = [
            {"service_type": "TEAMS", "enabled": True, "webhook_url": "https://outlook.com/x", "event_types": ["NEW_JOB"]},
        ]
        svc = NotificationService(mock_db)
        with patch.object(svc, "_send_teams_notification", new_callable=AsyncMock, return_value=True):
            result = await svc.send_notification("NEW_JOB", {"repository": "r"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_save_event_failure_continues(self, mock_db):
        mock_db.get_notification_configs.return_value = [
            {"service_type": "TEAMS", "enabled": True, "webhook_url": "https://x", "event_types": ["TEST"]},
        ]
        mock_db.save_notification_event.side_effect = Exception("db save failed")
        svc = NotificationService(mock_db)
        with patch.object(svc, "_send_teams_notification", new_callable=AsyncMock, return_value=True):
            result = await svc.send_notification("TEST", {"message": "hi"})
        assert result is True

    @pytest.mark.asyncio
    async def test_send_normalizes_lowercase_service_type(self, mock_db):
        mock_db.get_notification_configs.return_value = [
            {"service_type": "teams", "enabled": True, "webhook_url": "https://x", "event_types": ["new_job"]},
        ]
        svc = NotificationService(mock_db)
        with patch.object(svc, "_send_teams_notification", new_callable=AsyncMock, return_value=True) as send_mock:
            result = await svc.send_notification("NEW_JOB", {"repository": "r"})
        assert result is True
        send_mock.assert_awaited_once()


class TestNotificationConfigMethods:
    def test_get_notification_configs(self, mock_db):
        mock_db.get_notification_configs.return_value = [{"id": 1}]
        svc = NotificationService(mock_db)
        configs = svc.get_notification_configs()
        assert configs == [{"id": 1}]

    def test_get_notification_configs_exception(self, mock_db):
        mock_db.get_notification_configs.side_effect = Exception("err")
        svc = NotificationService(mock_db)
        assert svc.get_notification_configs() == []

    def test_save_notification_config(self, mock_db):
        svc = NotificationService(mock_db)
        out = svc.save_notification_config({"service_type": "TEAMS", "webhook_url": "https://x"})
        assert out is True
        mock_db.save_notification_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_notification_config_uses_only_target_config(self, mock_db):
        svc = NotificationService(mock_db)
        cfg = {"service_type": "EMAIL", "smtp_server": "smtp.example.com", "smtp_port": 587}
        with patch.object(svc, "_send_email_notification", new_callable=AsyncMock, return_value=True) as email_mock, \
             patch.object(svc, "_send_slack_notification", new_callable=AsyncMock, return_value=True) as slack_mock, \
             patch.object(svc, "_send_teams_notification", new_callable=AsyncMock, return_value=True) as teams_mock:
            result = await svc.test_notification_config(cfg)
        assert result is True
        email_mock.assert_awaited_once()
        slack_mock.assert_not_called()
        teams_mock.assert_not_called()
