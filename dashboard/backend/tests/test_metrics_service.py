"""
Unit tests for MetricsService: get_or_create_config, update_config, get_or_create_aggregate.
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, initialize_database
from services.metrics_service import MetricsService


@pytest.fixture(scope="module")
def ensure_db():
    initialize_database()
    yield


@pytest.fixture
def db_session(ensure_db):
    with SessionLocal() as session:
        yield session


@pytest.fixture
def metrics_service():
    return MetricsService()


@pytest.mark.asyncio
class TestMetricsService:
    async def test_get_or_create_config_returns_config(self, metrics_service, db_session):
        config = await metrics_service.get_or_create_config(db_session)
        assert config is not None
        assert hasattr(config, "developer_hourly_rate")
        assert config.developer_hourly_rate >= 0

    async def test_get_or_create_config_idempotent(self, metrics_service, db_session):
        c1 = await metrics_service.get_or_create_config(db_session)
        c2 = await metrics_service.get_or_create_config(db_session)
        assert c1.id == c2.id

    async def test_update_config_returns_config(self, metrics_service, db_session):
        await metrics_service.get_or_create_config(db_session)
        updated = await metrics_service.update_config(
            db_session,
            {"developer_hourly_rate": 100.0, "hours_multiplier": 1.5},
        )
        assert updated.developer_hourly_rate == 100.0
        assert updated.hours_multiplier == 1.5

    async def test_get_or_create_aggregate_returns_aggregate(self, metrics_service, db_session):
        agg = await metrics_service.get_or_create_aggregate(db_session)
        assert agg is not None
        assert hasattr(agg, "total_jobs")

    async def test_get_metrics_summary_returns_summary(self, metrics_service, db_session):
        summary = await metrics_service.get_metrics_summary(db_session)
        assert summary is not None
        assert hasattr(summary, "total_operations")
        assert hasattr(summary, "total_jobs")
        assert hasattr(summary, "total_token_cost")
        assert hasattr(summary, "model_breakdown")
        assert isinstance(summary.model_breakdown, dict)

    async def test_recalculate_metrics_from_operations(self, metrics_service, db_session):
        await metrics_service.recalculate_metrics_from_operations(db_session)
        summary = await metrics_service.get_metrics_summary(db_session)
        assert summary is not None

    async def test_get_operation_breakdown_returns_dict(self, metrics_service, db_session):
        breakdown = await metrics_service.get_operation_breakdown(db_session)
        assert isinstance(breakdown, dict)

    async def test_get_repository_breakdown_returns_dict(self, metrics_service, db_session):
        breakdown = await metrics_service.get_repository_breakdown(db_session)
        assert isinstance(breakdown, dict)

    async def test_update_metrics_from_operation_legacy_model(self, metrics_service, db_session):
        await metrics_service.get_or_create_config(db_session)
        await metrics_service.update_metrics_from_operation(
            db_session,
            {
                "model_used": "gpt-4",
                "input_tokens": 100,
                "output_tokens": 50,
                "job_id": "job-metrics-test",
                "estimated_dev_hours_saved": 0.5,
            },
        )
        summary = await metrics_service.get_metrics_summary(db_session)
        assert summary is not None
        assert summary.total_operations >= 1
        assert "gpt-4" in summary.model_breakdown
        assert summary.model_breakdown["gpt-4"]["input_tokens"] == 100
        assert summary.model_breakdown["gpt-4"]["output_tokens"] == 50

    async def test_update_metrics_from_operation_multi_model(self, metrics_service, db_session):
        await metrics_service.get_or_create_config(db_session)
        await metrics_service.update_metrics_from_operation(
            db_session,
            {
                "ai_models_used": {
                    "gpt-4": {"input_tokens": 200, "output_tokens": 100},
                    "gpt-3.5-turbo": {"input_tokens": 50, "output_tokens": 25},
                },
                "total_input_tokens": 250,
                "total_output_tokens": 125,
                "job_id": "job-multi-test",
                "estimated_dev_hours_saved": 0.25,
            },
        )
        summary = await metrics_service.get_metrics_summary(db_session)
        assert summary is not None
        assert summary.total_operations >= 1
        assert "gpt-4" in summary.model_breakdown or "gpt-3.5-turbo" in summary.model_breakdown
        breakdown = summary.model_breakdown
        if "gpt-4" in breakdown:
            assert breakdown["gpt-4"]["input_tokens"] >= 0
        if "gpt-3.5-turbo" in breakdown:
            assert breakdown["gpt-3.5-turbo"]["input_tokens"] >= 0
