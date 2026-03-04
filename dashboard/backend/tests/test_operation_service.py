"""
Unit tests for OperationService (get_operations, get_operation, update_operation_status).
"""
import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from database import SessionLocal, initialize_database
from models import OperationDB
from services.operation_service import OperationService


@pytest.fixture(scope="module")
def ensure_db():
    initialize_database()
    yield


@pytest.fixture
def db_session(ensure_db):
    with SessionLocal() as session:
        yield session


@pytest.fixture
def operation_service():
    return OperationService()


@pytest.mark.asyncio
class TestOperationService:
    async def test_get_operations_empty(self, operation_service, db_session):
        result = await operation_service.get_operations(db_session, limit=10)
        assert result.total >= 0
        assert "operations" in result.data
        assert isinstance(result.data["operations"], list)

    async def test_get_operation_not_found(self, operation_service, db_session):
        result = await operation_service.get_operation(db_session, "nonexistent-op-id-999")
        assert result is None

    async def test_update_operation_status_no_operation_id(self, operation_service, db_session):
        await operation_service.update_operation_status(db_session, {"status": "completed"})
        # No exception, no-op when operation_id missing

    async def test_update_operation_status_nonexistent_id(self, operation_service, db_session):
        await operation_service.update_operation_status(
            db_session, {"operation_id": "nonexistent-999", "status": "completed"}
        )
        # No exception

    async def test_get_operations_with_status_filter(self, operation_service, db_session):
        result = await operation_service.get_operations(db_session, limit=5, status="completed")
        assert result.total >= 0
        assert "operations" in result.data

    async def test_get_operations_with_repo_filter(self, operation_service, db_session):
        result = await operation_service.get_operations(db_session, limit=5, repo="some/repo")
        assert result.total >= 0
        assert isinstance(result.data["operations"], list)

    async def test_update_operation_status_existing_operation(self, operation_service, db_session):
        op = OperationDB(
            operation_id="op-status-test-123",
            job_id="job-1",
            repo="test/repo",
            operation_type="review",
            status="in_progress",
            started_at=datetime.utcnow(),
        )
        db_session.add(op)
        db_session.commit()
        db_session.refresh(op)
        await operation_service.update_operation_status(
            db_session,
            {"operation_id": "op-status-test-123", "status": "completed"},
        )
        db_session.refresh(op)
        assert op.status == "completed"
        assert op.completed_at is not None
