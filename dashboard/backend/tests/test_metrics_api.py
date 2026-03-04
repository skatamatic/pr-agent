"""
Tests for metrics API: summary, config, recalculate, operation/repository breakdowns.
Production-critical for cost and usage reporting.
"""
import pytest


class TestMetricsAPI:
    """Metrics read and recalculate endpoints."""

    def test_get_metrics_summary_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/metrics/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], dict)

    def test_get_metrics_config_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/metrics/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        config = data["data"]
        assert "model_costs" in config or "developer_hourly_rate" in config or isinstance(config, dict)

    def test_post_metrics_recalculate_returns_200(self, client_app, auth_headers):
        response = client_app.post("/api/metrics/recalculate", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "message" in data

    def test_get_metrics_operations_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/metrics/operations", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_get_metrics_repositories_returns_200(self, client_app, auth_headers):
        response = client_app.get("/api/metrics/repositories", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
