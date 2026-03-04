"""
Pytest configuration and fixtures for dashboard backend tests
"""
import os
import sys

# Use in-memory SQLite for all tests so we don't touch the real DB (must be before any dashboard imports)
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("DASHBOARD_DATABASE_URL", "")
# Cron secret for testing cron endpoints (so we can test 401 vs 200)
os.environ.setdefault("DASHBOARD_CRON_SECRET", "test-cron-secret")

import pytest
import tempfile
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base, JobDB, OperationDB, LogEntryDB, NotificationEventDB, MetricsAggregateDB
from services.job_deletion_service import JobDeletionService
from services.data_cleanup_service import DataCleanupService
from services.metrics_service import MetricsService
from services.retention_service import RetentionService


@pytest.fixture
def client_app():
    """Test client using real app with in-memory DB (env set at conftest load)."""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client_app):
    """Login as default admin and return headers with Bearer token for protected endpoints."""
    response = client_app.post(
        "/api/auth/login",
        json={"username": "admin", "password": "mobile"},
    )
    assert response.status_code == 200
    token = response.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_db():
    """Create a temporary in-memory SQLite database for testing"""
    # Create temporary database
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    # Cleanup
    session.close()
    engine.dispose()


@pytest.fixture
def mock_database_manager(test_db):
    """Mock database manager that returns our test database for SessionLocal() and get_session"""
    manager = Mock()
    manager.get_session.return_value.__enter__ = Mock(return_value=test_db)
    manager.get_session.return_value.__exit__ = Mock(return_value=None)
    # Services like DataCleanupService and JobDeletionService use database_manager.SessionLocal()
    manager.SessionLocal.return_value.__enter__ = Mock(return_value=test_db)
    manager.SessionLocal.return_value.__exit__ = Mock(return_value=None)
    return manager


@pytest.fixture
def mock_metrics_service():
    """Mock metrics service"""
    service = Mock(spec=MetricsService)
    service.get_or_create_config = AsyncMock(return_value=Mock(
        model_costs={
            'gpt-4': {'input': 0.03, 'output': 0.06},
            'gpt-3.5-turbo': {'input': 0.001, 'output': 0.002}
        },
        developer_hourly_rate=75.0,
        hours_multiplier=1.0
    ))
    service.recalculate_metrics_from_operations = AsyncMock()
    return service


@pytest.fixture
def mock_retention_service():
    """Mock retention service (create_backup is sync in real service)"""
    service = Mock(spec=RetentionService)
    service.create_backup = Mock(return_value={
        'success': True,
        'file_path': '/tmp/test_backup.db.gz',
        'path': '/tmp/test_backup.db.gz',
        'size': 0,
    })
    return service


@pytest.fixture
def sample_job_data():
    """Sample job data for testing"""
    return {
        'job_id': 'test-job-123',
        'job_type': 'review',
        'repository': 'test/repo',
        'status': 'completed',
        'started_at': datetime.now() - timedelta(days=1),
        'completed_at': datetime.now() - timedelta(hours=1)
    }


@pytest.fixture
def sample_operation_data():
    """Sample operation data for testing"""
    return {
        'operation_id': 'test-op-123',
        'job_id': 'test-job-123',
        'repo': 'test/repo',
        'operation_type': 'review',
        'model_used': 'gpt-4',
        'input_tokens': 1000,
        'output_tokens': 500,
        'total_input_tokens': 1000,
        'total_output_tokens': 500,
        'estimated_dev_hours_saved': 2.5,
        'started_at': datetime.now() - timedelta(days=1),
        'completed_at': datetime.now() - timedelta(hours=1)
    }


@pytest.fixture
def sample_log_data():
    """Sample log data for testing"""
    return {
        'job_id': 'test-job-123',
        'repo': 'test/repo',
        'level': 'INFO',
        'message': 'Test log message',
        'timestamp': datetime.now() - timedelta(days=1)
    }


@pytest.fixture
def sample_notification_data():
    """Sample notification data for testing"""
    return {
        'event_type': 'new_job',
        'event_data': {'job_id': 'test-job-123'},
        'repositories': ['test/repo'],
        'timestamp': datetime.now() - timedelta(days=1),
        'processed': False
    }


@pytest.fixture
def populated_test_db(test_db, sample_job_data, sample_operation_data, sample_log_data, sample_notification_data):
    """Populate test database with sample data"""
    # Create job
    job = JobDB(**sample_job_data)
    test_db.add(job)
    
    # Create operation
    operation = OperationDB(**sample_operation_data)
    test_db.add(operation)
    
    # Create log entries
    for i in range(3):
        log_data = sample_log_data.copy()
        log_data['message'] = f'Test log message {i}'
        log = LogEntryDB(**log_data)
        test_db.add(log)
    
    # Create notification events
    for i in range(2):
        notif_data = sample_notification_data.copy()
        notif_data['event_data'] = {'job_id': f'test-job-{i}'}
        notification = NotificationEventDB(**notif_data)
        test_db.add(notification)
    
    # Create metrics aggregate
    metrics = MetricsAggregateDB(
        total_jobs=1,
        total_operations=1,
        total_input_tokens=1000,
        total_output_tokens=500,
        total_estimated_dev_hours=2.5,
        model_usage={'gpt-4': {'operations_count': 1, 'input_tokens': 1000, 'output_tokens': 500}},
        last_updated=datetime.now()
    )
    test_db.add(metrics)
    
    test_db.commit()
    return test_db

