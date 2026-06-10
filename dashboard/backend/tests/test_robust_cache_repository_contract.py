"""
Unit tests for canonical `repository` on log/operation cache paths (no real DB writes).
Uses mocks for LogEntryDB and session.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from services.robust_cache_service import (
    AsyncPersistenceQueue,
    CacheEntry,
    LRUCache,
    RobustCacheService,
)


@pytest.mark.asyncio
class TestAsyncPersistenceLogRepository:
    async def test_handle_log_insert_strips_legacy_repo_key(self):
        queue = AsyncPersistenceQueue(MagicMock())
        db = MagicMock()

        payload = {
            "level": "INFO",
            "message": "test",
            "timestamp": datetime.utcnow(),
            "repository": "owner/name",
            "repo": "should-be-stripped",
        }

        with patch("models.LogEntryDB") as MockLog:
            instance = MagicMock()
            instance.id = 42
            MockLog.return_value = instance

            log_id = await queue._handle_log_operation(db, "insert", payload, None)

        assert log_id == 42
        kwargs = MockLog.call_args.kwargs
        assert kwargs.get("repository") == "owner/name"
        assert "repo" not in kwargs
        db.add.assert_called_once()
        db.flush.assert_called_once()


class TestRobustCacheServiceSerializers:
    def test_log_db_to_dict_exposes_repository_only(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        mock_log = MagicMock()
        mock_log.id = 1
        mock_log.timestamp = datetime.utcnow()
        mock_log.level = "INFO"
        mock_log.message = "m"
        mock_log.module = "mod"
        mock_log.app_name = None
        mock_log.job_id = None
        mock_log.operation_id = None
        mock_log.repository = "a/b"
        mock_log.status = None
        mock_log.function = None
        mock_log.line = None
        mock_log.pr_url = None
        mock_log.command = None
        mock_log.installation_id = None
        mock_log.sender = None
        mock_log.request_id = None
        mock_log.sub_feature = None
        mock_log.analytics = False
        mock_log.git_provider = None
        mock_log.artifact = None
        mock_log.artifacts = None
        mock_log.error = None
        mock_log.build_number = None
        mock_log.received_at = None

        d = svc._log_db_to_dict(mock_log)

        assert d.get("repository") == "a/b"
        assert "repo" not in d

    def test_operation_db_to_dict_exposes_repository_only(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        op = MagicMock()
        op.operation_id = "op-1"
        op.job_id = "j-1"
        op.operation_type = "review"
        op.command = "c"
        op.status = "completed"
        op.repository = "org/proj"
        op.pr_url = None
        op.installation_id = None
        op.sender = None
        op.request_id = None
        op.started_at = None
        op.completed_at = None
        op.last_updated = None
        op.duration = None
        op.error_details = None
        op.result_data = None
        op.model_used = None
        op.input_tokens = None
        op.output_tokens = None
        op.estimated_dev_hours_saved = None
        op.current_step = None
        op.ai_models_used = None
        op.total_input_tokens = None
        op.total_output_tokens = None
        op.insights = None

        d = svc._operation_db_to_dict(op)

        assert d.get("repository") == "org/proj"
        assert "repo" not in d


class TestGetLogsFromCacheRepositoryFilter:
    """In-memory cache only — no SQLite."""

    @pytest.mark.asyncio
    async def test_get_logs_from_cache_filters_by_repository(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        svc.logs_cache = LRUCache(max_entries=100, max_memory_mb=16)

        await svc.logs_cache.put(
            "1",
            CacheEntry(
                data={
                    "id": 1,
                    "level": "INFO",
                    "message": "a",
                    "timestamp": "2025-06-01T12:00:00",
                    "repository": "alpha/beta",
                }
            ),
        )
        await svc.logs_cache.put(
            "2",
            CacheEntry(
                data={
                    "id": 2,
                    "level": "INFO",
                    "message": "b",
                    "timestamp": "2025-06-02T12:00:00",
                    "repository": "other/repo",
                }
            ),
        )

        results = await svc._get_logs_from_cache(10, repository="alpha/beta")
        assert len(results) == 1
        assert results[0]["repository"] == "alpha/beta"
