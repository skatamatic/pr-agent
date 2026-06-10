"""
Comprehensive unit tests for services.robust_cache_service.

Focus: LRU / CacheEntry / stats, AsyncPersistenceQueue helpers and enqueue,
RobustCacheService cache-through operations (jobs, operations, logs) without
starting background workers unless patched.

Run with coverage:
  pytest tests/test_robust_cache_service_comprehensive.py --cov=services.robust_cache_service --cov-report=term-missing
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.robust_cache_service import (
    AsyncPersistenceQueue,
    CacheEntry,
    CacheStats,
    LRUCache,
    RobustCacheService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ensure_db_schema():
    """Ensure SQLAlchemy models exist on the shared in-memory engine (conftest sets DATABASE_URL)."""
    from database import Base, engine

    Base.metadata.create_all(bind=engine)
    yield
    # Keep tables for the rest of the test session; in-memory DB is process-local.


@pytest.fixture
def rcs() -> RobustCacheService:
    """RobustCacheService with persistence enqueue mocked — no background tasks."""
    svc = RobustCacheService(MagicMock())
    svc.persistence_queue.enqueue_operation = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# CacheEntry, CacheStats, LRUCache
# ---------------------------------------------------------------------------


class TestCacheStats:
    def test_hit_rate_zero_when_no_requests(self):
        s = CacheStats()
        assert s.hit_rate == 0.0

    def test_hit_rate_computed(self):
        s = CacheStats(hits=3, misses=7)
        assert s.hit_rate == 30.0

    def test_memory_usage_mb(self):
        s = CacheStats(memory_usage_bytes=2 * 1024 * 1024)
        assert s.memory_usage_mb == 2.0


class TestCacheEntry:
    def test_mark_accessed_increments(self):
        e = CacheEntry(data={"a": 1})
        assert e.access_count == 0
        e.mark_accessed()
        assert e.access_count == 1

    def test_mark_dirty_sets_dirty(self):
        e = CacheEntry(data={"x": 1}, dirty=False)
        e.mark_dirty()
        assert e.dirty is True


@pytest.mark.asyncio
class TestLRUCache:
    async def test_get_miss_and_hit(self):
        c = LRUCache(max_entries=10, max_memory_mb=64)
        assert await c.get("missing") is None
        assert c.stats.misses == 1

        await c.put("k", CacheEntry(data=1))
        ent = await c.get("k")
        assert ent is not None
        assert ent.data == 1
        assert c.stats.hits == 1

    async def test_put_replace_adjusts_memory_stats(self):
        c = LRUCache(max_entries=10, max_memory_mb=64)
        await c.put("k", CacheEntry(data="small"))
        mem1 = c.stats.memory_usage_bytes
        await c.put("k", CacheEntry(data="x" * 5000))
        assert c.stats.memory_usage_bytes != mem1

    async def test_remove_and_clear(self):
        c = LRUCache(max_entries=10, max_memory_mb=64)
        await c.put("a", CacheEntry(data=1))
        assert await c.remove("a") is True
        assert await c.remove("a") is False
        await c.put("b", CacheEntry(data=2))
        await c.clear()
        assert len(c.entries) == 0
        assert c.stats.entry_count == 0

    async def test_eviction_when_over_max_entries(self):
        c = LRUCache(max_entries=2, max_memory_mb=256)
        await c.put("1", CacheEntry(data={"n": 1}))
        await c.put("2", CacheEntry(data={"n": 2}))
        await c.put("3", CacheEntry(data={"n": 3}))
        assert len(c.entries) == 2
        assert "1" not in c.entries
        assert c.stats.evictions >= 1


# ---------------------------------------------------------------------------
# AsyncPersistenceQueue
# ---------------------------------------------------------------------------


class TestAsyncPersistenceQueueHelpers:
    def test_convert_datetime_strings_parses_iso(self):
        q = AsyncPersistenceQueue(MagicMock())
        raw = {
            "started_at": "2025-03-01T12:00:00Z",
            "completed_at": "2025-03-01T13:00:00+00:00",
            "timestamp": "2025-03-01T14:00:00",
            "other": "unchanged",
        }
        out = q._convert_datetime_strings(raw)
        assert isinstance(out["started_at"], datetime)
        assert isinstance(out["completed_at"], datetime)
        assert isinstance(out["timestamp"], datetime)
        assert out["other"] == "unchanged"

    @pytest.mark.asyncio
    async def test_execute_database_operation_unknown_table(self):
        q = AsyncPersistenceQueue(MagicMock())
        db = MagicMock()
        with pytest.raises(ValueError, match="Unknown table"):
            await q._execute_database_operation(
                db,
                {"table": "unknown_table", "type": "insert", "data": {}},
            )

    @pytest.mark.asyncio
    async def test_enqueue_operation_structure(self):
        q = AsyncPersistenceQueue(MagicMock())
        await q.enqueue_operation(
            "insert",
            "jobs",
            {"job_id": "j1", "job_type": "cli", "source": "t", "status": "running"},
            key=None,
            priority=5,
        )
        op = q.queue.get_nowait()
        assert op["type"] == "insert"
        assert op["table"] == "jobs"
        assert op["priority"] == 5
        assert op["data"]["job_id"] == "j1"

    @pytest.mark.asyncio
    async def test_flush_empty_queues(self):
        q = AsyncPersistenceQueue(MagicMock())
        result = await q.flush(timeout_seconds=0.15)
        assert result["processed"] == 0
        assert result["queue_remaining"] == 0
        assert result["retry_remaining"] == 0

    @pytest.mark.asyncio
    async def test_flush_processes_batch(self):
        q = AsyncPersistenceQueue(MagicMock())
        await q.enqueue_operation("insert", "jobs", {"job_id": "x", "job_type": "cli", "source": "s", "status": "running"})

        async def fake_batch(ops):
            return (ops, [])

        with patch.object(q, "_process_operations_batch", side_effect=fake_batch):
            result = await q.flush(timeout_seconds=2.0)
        assert result["processed"] >= 1


# ---------------------------------------------------------------------------
# RobustCacheService — serializers & indexes
# ---------------------------------------------------------------------------


class TestRobustCacheServiceSerializersExtended:
    def test_job_db_to_dict(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        job = SimpleNamespace(
            job_id="job-1",
            job_type="webhook",
            source="gh",
            status="running",
            repository="o/r",
            pr_url="http://p",
            trigger_user="u",
            trigger_event="pr",
            installation_id="1",
            request_id="r1",
            webhook_payload=None,
            started_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            completed_at=None,
            last_updated=datetime(2025, 1, 2, tzinfo=timezone.utc),
            duration=None,
            operations_count=0,
            completed_operations=0,
            failed_operations=0,
            total_logs=0,
            error_count=0,
            warning_count=0,
            result_summary=None,
            error_details=None,
        )
        d = svc._job_db_to_dict(job)
        assert d["job_id"] == "job-1"
        assert d["repository"] == "o/r"

    @pytest.mark.asyncio
    async def test_update_job_indexes(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        svc.jobs_by_status = {}
        svc.jobs_by_repository = {}
        from collections import defaultdict

        svc.jobs_by_status = defaultdict(set)
        svc.jobs_by_repository = defaultdict(set)
        await svc._update_job_indexes(
            "jid",
            {"status": "running", "repository": "a/b"},
        )
        assert "jid" in svc.jobs_by_status["running"]
        assert "jid" in svc.jobs_by_repository["a/b"]

    @pytest.mark.asyncio
    async def test_remove_job_from_indexes(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        from collections import defaultdict

        svc.jobs_by_status = defaultdict(set, {"running": {"j1"}})
        svc.jobs_by_repository = defaultdict(set, {"x/y": {"j1"}})
        await svc._remove_job_from_indexes("j1")
        assert "j1" not in svc.jobs_by_status["running"]
        assert "j1" not in svc.jobs_by_repository["x/y"]


# ---------------------------------------------------------------------------
# RobustCacheService — jobs / operations (cache only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRobustCacheServiceJobs:
    async def test_create_get_job(self, rcs: RobustCacheService):
        await rcs.create_job(
            {
                "job_id": "job-a",
                "job_type": "cli",
                "source": "test",
                "status": "running",
                "repository": "org/repo",
                "started_at": "2025-01-01T00:00:00Z",
            }
        )
        j = await rcs.get_job("job-a")
        assert j["job_id"] == "job-a"
        assert j["repository"] == "org/repo"
        rcs.persistence_queue.enqueue_operation.assert_called()

    async def test_update_job_moves_indexes(self, rcs: RobustCacheService):
        await rcs.create_job(
            {
                "job_id": "job-b",
                "job_type": "cli",
                "source": "test",
                "status": "running",
                "repository": "old/r",
                "started_at": "2025-01-01T00:00:00Z",
            }
        )
        ok = await rcs.update_job(
            "job-b",
            {"status": "completed", "repository": "new/r"},
        )
        assert ok is True
        assert "job-b" in rcs.jobs_by_status["completed"]
        assert "job-b" not in rcs.jobs_by_status.get("running", set())
        assert "job-b" in rcs.jobs_by_repository["new/r"]

    async def test_update_job_missing_returns_false(self, rcs: RobustCacheService):
        assert await rcs.update_job("nope", {"status": "x"}) is False

    async def test_get_jobs_merges_cache_and_db(self, rcs: RobustCacheService):
        await rcs.create_job(
            {
                "job_id": "cache-only",
                "job_type": "cli",
                "source": "s",
                "status": "running",
                "started_at": "2025-06-01T00:00:00Z",
            }
        )
        with patch.object(
            rcs,
            "_get_jobs_from_db",
            new_callable=AsyncMock,
            return_value=[],
        ):
            jobs = await rcs.get_jobs(limit=10)
        ids = {j["job_id"] for j in jobs}
        assert "cache-only" in ids

    async def test_get_jobs_from_cache_by_status(self, rcs: RobustCacheService):
        await rcs.create_job(
            {
                "job_id": "j-status",
                "job_type": "cli",
                "source": "s",
                "status": "queued",
                "started_at": "2025-05-01T00:00:00Z",
            }
        )
        cached = await rcs._get_jobs_from_cache(10, status="queued")
        assert len(cached) == 1
        assert cached[0]["job_id"] == "j-status"

    async def test_get_jobs_from_cache_extra_filter(self, rcs: RobustCacheService):
        await rcs.create_job(
            {
                "job_id": "jf",
                "job_type": "api",
                "source": "s",
                "status": "running",
                "started_at": "2025-05-01T00:00:00Z",
            }
        )
        cached = await rcs._get_jobs_from_cache(10, job_type="api")
        assert len(cached) == 1


@pytest.mark.asyncio
class TestRobustCacheServiceOperations:
    async def test_create_get_update_operation(self, rcs: RobustCacheService):
        await rcs.create_operation(
            {
                "operation_id": "op-1",
                "job_id": "job-1",
                "operation_type": "review",
                "command": "review",
                "status": "running",
                "repository": "a/b",
                "started_at": "2025-01-01T00:00:00Z",
            }
        )
        op = await rcs.get_operation("op-1")
        assert op["operation_id"] == "op-1"
        ok = await rcs.update_operation(
            "op-1",
            {"status": "completed", "job_id": "job-2"},
        )
        assert ok is True
        assert "op-1" in rcs.operations_by_status["completed"]
        assert "op-1" in rcs.operations_by_job["job-2"]

    async def test_get_operations_from_cache_by_job(self, rcs: RobustCacheService):
        await rcs.create_operation(
            {
                "operation_id": "op-j",
                "job_id": "job-x",
                "operation_type": "review",
                "command": "c",
                "status": "running",
                "started_at": "2025-01-01T00:00:00Z",
            }
        )
        rows = await rcs._get_operations_from_cache(10, job_id="job-x")
        assert len(rows) == 1
        assert rows[0]["operation_id"] == "op-j"

    async def test_get_operations_from_cache_by_status(self, rcs: RobustCacheService):
        await rcs.create_operation(
            {
                "operation_id": "op-s",
                "job_id": "j1",
                "operation_type": "review",
                "command": "c",
                "status": "pending",
                "started_at": "2025-02-01T00:00:00Z",
            }
        )
        rows = await rcs._get_operations_from_cache(10, status="pending")
        assert any(r["operation_id"] == "op-s" for r in rows)

    async def test_update_operation_missing_returns_false(self, rcs: RobustCacheService):
        assert await rcs.update_operation("missing-op", {"status": "x"}) is False


# ---------------------------------------------------------------------------
# Logs — cache paths & get_logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRobustCacheServiceLogs:
    async def test_get_logs_from_cache_by_job_id(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        svc.logs_cache = LRUCache(max_entries=100, max_memory_mb=32)
        from collections import defaultdict

        svc.logs_by_job = defaultdict(set)
        svc.logs_by_operation = defaultdict(set)
        svc.logs_by_job["job-1"].add(10)
        await svc.logs_cache.put(
            "10",
            CacheEntry(
                data={
                    "id": 10,
                    "level": "INFO",
                    "message": "m",
                    "timestamp": "2025-01-01T10:00:00",
                    "job_id": "job-1",
                }
            ),
        )
        rows = await svc._get_logs_from_cache(5, job_id="job-1")
        assert len(rows) == 1
        assert rows[0]["id"] == 10

    async def test_get_logs_from_cache_search_filter(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        svc.logs_cache = LRUCache(max_entries=100, max_memory_mb=32)
        from collections import defaultdict

        svc.logs_by_job = defaultdict(set)
        svc.logs_by_operation = defaultdict(set)
        await svc.logs_cache.put(
            "1",
            CacheEntry(
                data={
                    "id": 1,
                    "level": "INFO",
                    "message": "needle-in-haystack",
                    "module": "mod",
                    "source": "src",
                    "timestamp": "2025-01-02T10:00:00",
                }
            ),
        )
        rows = await svc._get_logs_from_cache(10, search="needle")
        assert len(rows) == 1

    async def test_get_logs_merge_offset_and_search(self, rcs: RobustCacheService):
        with patch.object(
            rcs,
            "_get_logs_from_cache",
            new_callable=AsyncMock,
            return_value=[
                {
                    "id": 1,
                    "timestamp": "2025-01-10T00:00:00",
                    "message": "alpha",
                    "module": "",
                    "source": "",
                },
                {
                    "id": 2,
                    "timestamp": "2025-01-09T00:00:00",
                    "message": "beta-needle",
                    "module": "",
                    "source": "",
                },
            ],
        ):
            with patch.object(rcs, "_get_logs_from_db", new_callable=AsyncMock, return_value=[]):
                page = await rcs.get_logs(limit=5, offset=0, search="needle")
        assert len(page) == 1
        assert page[0]["id"] == 2


# ---------------------------------------------------------------------------
# Statistics, clear, DB error paths, force sync
# ---------------------------------------------------------------------------


class TestIsRecentLog:
    """Sync helper — keep outside @pytest.mark.asyncio classes."""

    def test_is_recent_log_true_and_false(self):
        svc = RobustCacheService.__new__(RobustCacheService)
        now = datetime.now(timezone.utc)
        recent = {
            "timestamp": now.replace(tzinfo=None).isoformat() + "Z",
        }
        assert svc._is_recent_log(recent) is True
        old = {
            "timestamp": (now - timedelta(days=10)).isoformat(),
        }
        assert svc._is_recent_log(old) is False


@pytest.mark.asyncio
class TestRobustCacheServiceUtilities:
    async def test_get_cache_statistics_shape(self, rcs: RobustCacheService):
        stats = await rcs.get_cache_statistics()
        assert "jobs" in stats and "operations" in stats and "logs" in stats
        assert "persistence" in stats
        assert "hit_rate" in stats["jobs"]

    async def test_clear_all_data(self, rcs: RobustCacheService):
        await rcs.create_job(
            {
                "job_id": "to-clear",
                "job_type": "cli",
                "source": "s",
                "status": "running",
                "started_at": "2025-01-01T00:00:00Z",
            }
        )
        await rcs.clear_all_data()
        assert rcs.jobs_cache.stats.entry_count == 0
        assert rcs.persistence_queue.enqueue_operation.call_count >= 3

    async def test_get_jobs_from_db_error_returns_empty(self):
        svc = RobustCacheService(MagicMock())
        with patch("database.SessionLocal", side_effect=RuntimeError("db down")):
            rows = await svc._get_jobs_from_db(5)
        assert rows == []

    async def test_load_job_from_db_error_returns_none(self):
        svc = RobustCacheService(MagicMock())
        with patch("database.SessionLocal", side_effect=RuntimeError("db down")):
            row = await svc._load_job_from_db("any")
        assert row is None

    async def test_get_logs_from_db_error_returns_empty(self):
        svc = RobustCacheService(MagicMock())
        with patch("database.SessionLocal", side_effect=RuntimeError("db down")):
            rows = await svc._get_logs_from_db(5)
        assert rows == []

    async def test_get_operations_from_db_error_returns_empty(self):
        svc = RobustCacheService(MagicMock())
        with patch("database.SessionLocal", side_effect=RuntimeError("db down")):
            rows = await svc._get_operations_from_db(5)
        assert rows == []

    async def test_load_operation_from_db_error_returns_none(self):
        svc = RobustCacheService(MagicMock())
        with patch("database.SessionLocal", side_effect=RuntimeError("db down")):
            row = await svc._load_operation_from_db("op-x")
        assert row is None

    async def test_force_sync_operation_to_db(self):
        svc = RobustCacheService(MagicMock())
        await svc.operations_cache.put(
            "op-fs",
            CacheEntry(
                data={
                    "operation_id": "op-fs",
                    "job_id": "j1",
                    "status": "completed",
                    "model_used": "gpt-test",
                    "input_tokens": 10,
                    "output_tokens": 20,
                }
            ),
        )
        mock_row = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_row

        with patch("database.SessionLocal", return_value=mock_db):
            ok = await svc.force_sync_operation_to_db("op-fs")
        assert ok is True
        mock_db.commit.assert_called_once()


@pytest.mark.asyncio
class TestRobustCacheServiceBackgroundHelpers:
    async def test_log_cache_statistics_runs(self, rcs: RobustCacheService):
        await rcs._log_cache_statistics()

    async def test_check_memory_pressure_high_usage(self, rcs: RobustCacheService):
        mock_mem = MagicMock()
        mock_mem.percent = 90.0
        with patch("services.robust_cache_service.psutil.virtual_memory", return_value=mock_mem):
            await rcs._check_memory_pressure()
        assert rcs.jobs_cache.max_memory_bytes < 64 * 1024 * 1024

    async def test_cleanup_expired_entries_removes_old_job(self, rcs: RobustCacheService):
        """Entry older than TTL cutoff is removed (cutoff ≈ now − cache_ttl)."""
        old_entry = CacheEntry(
            data={"job_id": "old"},
            dirty=False,
            created_at=datetime(2010, 1, 1),
        )
        await rcs.jobs_cache.put("old-job", old_entry)
        rcs.jobs_by_status["running"] = {"old-job"}

        await rcs._cleanup_expired_entries()

        assert await rcs.jobs_cache.get("old-job") is None


# ---------------------------------------------------------------------------
# Persistence: real SQLite inserts (schema required)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAsyncPersistenceWithDb:
    async def test_handle_job_insert_select(self, ensure_db_schema):
        queue = AsyncPersistenceQueue(MagicMock())
        from database import SessionLocal

        jid = f"job-{id(self)}"
        db = SessionLocal()
        try:
            await queue._handle_job_operation(
                db,
                "insert",
                {
                    "job_id": jid,
                    "job_type": "cli",
                    "source": "test",
                    "status": "running",
                },
            )
            db.commit()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            from models import JobDB

            row = db2.query(JobDB).filter(JobDB.job_id == jid).first()
            assert row is not None
            assert row.status == "running"
        finally:
            db2.close()

    async def test_create_log_round_trip(self, ensure_db_schema, rcs: RobustCacheService):
        """Uses real SessionLocal + LogEntryDB insert via persistence queue."""
        log_id = await rcs.create_log(
            {
                "level": "INFO",
                "message": "round-trip-msg",
                "timestamp": datetime.utcnow(),
            }
        )
        assert isinstance(log_id, int)
        ent = await rcs.logs_cache.get(str(log_id))
        assert ent.data["message"] == "round-trip-msg"

    async def test_create_logs_batch_round_trip(self, ensure_db_schema, rcs: RobustCacheService):
        ids = await rcs.create_logs_batch(
            [
                {"level": "INFO", "message": "batch-a", "timestamp": datetime.utcnow()},
                {"level": "WARN", "message": "batch-b", "timestamp": datetime.utcnow()},
            ]
        )
        assert len(ids) == 2
        messages = []
        for lid in ids:
            ent = await rcs.logs_cache.get(str(lid))
            messages.append(ent.data["message"])
        assert set(messages) == {"batch-a", "batch-b"}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


def test_get_robust_cache_service_singleton():
    import services.robust_cache_service as mod

    prev = mod.robust_cache_service
    try:
        mod.robust_cache_service = None
        with patch("database.DatabaseManager") as dm:
            dm.return_value = MagicMock()
            a = mod.get_robust_cache_service()
            b = mod.get_robust_cache_service()
            assert a is b
    finally:
        mod.robust_cache_service = prev
