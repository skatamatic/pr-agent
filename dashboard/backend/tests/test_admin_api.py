"""
Tests for admin API: retention config, database stats.
"""
import pytest


class TestAdminAPI:
    """Admin retention and database endpoints (require auth)."""

    def test_get_retention_config_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/admin/retention/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], dict)

    def test_get_database_stats_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/admin/database/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        stats = data["data"]
        assert "jobs_count" in stats or "table_stats" in stats or "size_mb" in stats
