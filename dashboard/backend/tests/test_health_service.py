"""
Unit tests for HealthService (_get_health_config_summary, _log_health_service_startup).
"""
import pytest
from unittest.mock import MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.health_service import HealthService


@pytest.fixture
def mock_database():
    return MagicMock()


@pytest.fixture
def health_service(mock_database):
    return HealthService(mock_database, notification_service=None, config_service=None)


class TestHealthService:
    def test_get_health_config_summary_returns_dict(self, health_service):
        result = health_service._get_health_config_summary()
        assert isinstance(result, dict)
        assert "services" in result
        assert "api" in result["services"] or "websocket" in result["services"]

    def test_log_health_service_startup_no_exception(self, health_service):
        health_service._log_health_service_startup()

    def test_log_health_service_shutdown_no_exception(self, health_service):
        health_service._log_health_service_shutdown()
