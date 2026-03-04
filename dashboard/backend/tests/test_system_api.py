"""
Tests for system/status API: realtime status, alerts, performance.
"""
import pytest


class TestSystemAPI:
    """System status and performance endpoints."""

    def test_get_status_realtime_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/status/realtime", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_system_alerts_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/system/alerts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_get_system_performance_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/system/performance", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
