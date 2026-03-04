"""
Tests for Data Cleanup Service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from services.data_cleanup_service import DataCleanupService
from models import JobDB, OperationDB, LogEntryDB, NotificationEventDB


class TestDataCleanupService:
    """Test cases for DataCleanupService"""
    
    @pytest.fixture
    def data_cleanup_service(self, mock_database_manager, mock_metrics_service, mock_retention_service):
        """Create DataCleanupService instance for testing"""
        return DataCleanupService(mock_database_manager, mock_metrics_service, mock_retention_service)
    
    @pytest.fixture
    def old_data_db(self, test_db):
        """Create database with old data for cleanup testing"""
        # Create old job (2 days ago)
        old_job = JobDB(
            job_id='old-job-123',
            job_type='review',
            repository='test/repo',
            status='completed',
            started_at=datetime.now() - timedelta(days=2),
            completed_at=datetime.now() - timedelta(days=2, hours=1)
        )
        test_db.add(old_job)
        
        # Create recent job (1 hour ago)
        recent_job = JobDB(
            job_id='recent-job-456',
            job_type='review',
            repository='test/repo',
            status='completed',
            started_at=datetime.now() - timedelta(hours=1),
            completed_at=datetime.now() - timedelta(minutes=30)
        )
        test_db.add(recent_job)
        
        # Create old operation (2 days ago)
        old_operation = OperationDB(
            operation_id='old-op-123',
            job_id='old-job-123',
            repo='test/repo',
            operation_type='review',
            model_used='gpt-4',
            input_tokens=1000,
            output_tokens=500,
            started_at=datetime.now() - timedelta(days=2),
            completed_at=datetime.now() - timedelta(days=2, hours=1)
        )
        test_db.add(old_operation)
        
        # Create recent operation (1 hour ago)
        recent_operation = OperationDB(
            operation_id='recent-op-456',
            job_id='recent-job-456',
            repo='test/repo',
            operation_type='review',
            model_used='gpt-4',
            input_tokens=800,
            output_tokens=400,
            started_at=datetime.now() - timedelta(hours=1),
            completed_at=datetime.now() - timedelta(minutes=30)
        )
        test_db.add(recent_operation)
        
        # Create old logs (2 days ago)
        for i in range(2):
            old_log = LogEntryDB(
                job_id='old-job-123',
                repo='test/repo',
                level='INFO',
                message=f'Old log message {i}',
                timestamp=datetime.now() - timedelta(days=2)
            )
            test_db.add(old_log)
        
        # Create recent logs (1 hour ago)
        for i in range(2):
            recent_log = LogEntryDB(
                job_id='recent-job-456',
                repo='test/repo',
                level='INFO',
                message=f'Recent log message {i}',
                timestamp=datetime.now() - timedelta(hours=1)
            )
            test_db.add(recent_log)
        
        # Create old notification events (2 days ago)
        for i in range(2):
            old_notification = NotificationEventDB(
                event_type='new_job',
                event_data={'job_id': f'old-job-{i}'},
                repositories=['test/repo'],
                timestamp=datetime.now() - timedelta(days=2),
                processed=False
            )
            test_db.add(old_notification)
        
        # Create recent notification events (1 hour ago)
        for i in range(2):
            recent_notification = NotificationEventDB(
                event_type='new_job',
                event_data={'job_id': f'recent-job-{i}'},
                repositories=['test/repo'],
                timestamp=datetime.now() - timedelta(hours=1),
                processed=False
            )
            test_db.add(recent_notification)
        
        test_db.commit()
        return test_db
    
    @pytest.mark.asyncio
    async def test_get_cleanup_preview_all_repositories(self, data_cleanup_service, old_data_db):
        """Test cleanup preview for all repositories"""
        cutoff_date = datetime.now() - timedelta(days=1)
        
        result = await data_cleanup_service.get_cleanup_preview(cutoff_date)
        
        assert result['cutoff_date'] == cutoff_date.isoformat()
        assert result['repository'] is None
        
        # Check before cleanup counts
        assert result['before_cleanup']['operations'] == 2
        assert result['before_cleanup']['jobs'] == 2
        assert result['before_cleanup']['logs'] == 4
        assert result['before_cleanup']['notification_events'] == 4
        
        # Check after cleanup counts (only recent data should remain)
        assert result['after_cleanup']['operations'] == 1
        assert result['after_cleanup']['jobs'] == 1
        assert result['after_cleanup']['logs'] == 2
        assert result['after_cleanup']['notification_events'] == 2
        
        # Check to be deleted counts
        assert result['to_be_deleted']['operations'] == 1
        assert result['to_be_deleted']['jobs'] == 1
        assert result['to_be_deleted']['logs'] == 2
        assert result['to_be_deleted']['notification_events'] == 2
        
        assert 'cost_impact' in result
        assert 'storage_impact_mb' in result
    
    @pytest.mark.asyncio
    async def test_get_cleanup_preview_specific_repository(self, data_cleanup_service, old_data_db):
        """Test cleanup preview for specific repository"""
        cutoff_date = datetime.now() - timedelta(days=1)
        repository = 'test/repo'
        
        result = await data_cleanup_service.get_cleanup_preview(cutoff_date, repository)
        
        assert result['repository'] == repository
        # Should have same counts as all repositories since all data is for 'test/repo'
        assert result['before_cleanup']['operations'] == 2
        assert result['after_cleanup']['operations'] == 1
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_success(self, data_cleanup_service, old_data_db):
        """Test successful cleanup execution"""
        cutoff_date = datetime.now() - timedelta(days=1)
        
        result = await data_cleanup_service.execute_cleanup(cutoff_date)
        
        assert result['cutoff_date'] == cutoff_date.isoformat()
        assert result['repository'] is None
        assert 'backup_path' in result
        assert result['message'] == "Data cleanup completed successfully"
        
        # Check deleted counts
        assert result['deleted_counts']['operations'] == 1
        assert result['deleted_counts']['jobs'] == 1
        assert result['deleted_counts']['logs'] == 2
        assert result['deleted_counts']['notification_events'] == 2
        
        # Verify old data was actually deleted
        old_job = old_data_db.query(JobDB).filter(JobDB.job_id == 'old-job-123').first()
        assert old_job is None
        
        old_operation = old_data_db.query(OperationDB).filter(OperationDB.operation_id == 'old-op-123').first()
        assert old_operation is None
        
        # Verify recent data still exists
        recent_job = old_data_db.query(JobDB).filter(JobDB.job_id == 'recent-job-456').first()
        assert recent_job is not None
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_with_data_types_filter(self, data_cleanup_service, old_data_db):
        """Test cleanup execution with specific data types"""
        cutoff_date = datetime.now() - timedelta(days=1)
        data_types = ['operations', 'logs']  # Only clean operations and logs
        
        result = await data_cleanup_service.execute_cleanup(cutoff_date, data_types=data_types)
        
        # Check only specified data types were deleted
        assert result['deleted_counts']['operations'] == 1
        assert result['deleted_counts']['logs'] == 2
        assert result['deleted_counts'].get('jobs', 0) == 0  # Jobs not in data_types
        assert result['deleted_counts'].get('notification_events', 0) == 0  # Not in data_types
        
        # Verify jobs were not deleted
        old_job = old_data_db.query(JobDB).filter(JobDB.job_id == 'old-job-123').first()
        assert old_job is not None  # Should still exist
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_backup_creation(self, data_cleanup_service, old_data_db):
        """Test that backup is created before cleanup"""
        cutoff_date = datetime.now() - timedelta(days=1)
        
        await data_cleanup_service.execute_cleanup(cutoff_date)
        
        # Verify backup service was called
        data_cleanup_service.retention_service.create_backup.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_metrics_recalculation(self, data_cleanup_service, old_data_db):
        """Test that metrics are recalculated after cleanup"""
        cutoff_date = datetime.now() - timedelta(days=1)
        
        await data_cleanup_service.execute_cleanup(cutoff_date)
        
        # Verify metrics service was called
        data_cleanup_service.metrics_service.recalculate_metrics_from_operations.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_calculate_storage_impact(self, data_cleanup_service, old_data_db):
        """Test storage impact calculation"""
        cutoff_date = datetime.now() - timedelta(days=1)
        
        storage_impact = await data_cleanup_service._calculate_storage_impact(old_data_db, cutoff_date)
        
        # Should return a non-negative number (estimated MB freed)
        assert storage_impact >= 0
        assert isinstance(storage_impact, float)
    
    @pytest.mark.asyncio
    async def test_get_current_cost_savings(self, data_cleanup_service, old_data_db):
        """Test current cost savings calculation"""
        cost_savings = await data_cleanup_service._get_current_cost_savings(old_data_db)
        
        # Should calculate cost based on all operations (may be 0 if no operations with tokens)
        assert cost_savings >= 0
        assert isinstance(cost_savings, float)
    
    @pytest.mark.asyncio
    async def test_get_remaining_cost_savings(self, data_cleanup_service, old_data_db):
        """Test remaining cost savings calculation after cutoff"""
        cutoff_date = datetime.now() - timedelta(days=1)
        
        remaining_savings = await data_cleanup_service._get_remaining_cost_savings(old_data_db, cutoff_date)
        
        # Should calculate cost based on remaining operations only
        assert remaining_savings >= 0
        assert isinstance(remaining_savings, float)
        # Should be less than or equal to current savings since we're excluding old data
        current_savings = await data_cleanup_service._get_current_cost_savings(old_data_db)
        # Allow for small floating point differences
        assert abs(remaining_savings - current_savings) < 0.1 or remaining_savings <= current_savings
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_database_rollback_on_error(self, data_cleanup_service, old_data_db):
        """Test that database rollback occurs on cleanup error"""
        # Mock the metrics service to raise an exception
        data_cleanup_service.metrics_service.recalculate_metrics_from_operations.side_effect = Exception("Database error")
        
        cutoff_date = datetime.now() - timedelta(days=1)
        
        # The service should handle the error and re-raise it
        with pytest.raises(Exception):
            await data_cleanup_service.execute_cleanup(cutoff_date)
    
    @pytest.mark.asyncio
    async def test_execute_cleanup_backup_failure(self, data_cleanup_service, old_data_db):
        """Test cleanup when backup creation fails"""
        # Mock backup service to raise an exception
        data_cleanup_service.retention_service.create_backup.side_effect = Exception("Backup failed")
        
        cutoff_date = datetime.now() - timedelta(days=1)
        
        # The service should handle the error and re-raise it
        with pytest.raises(Exception):
            await data_cleanup_service.execute_cleanup(cutoff_date)
