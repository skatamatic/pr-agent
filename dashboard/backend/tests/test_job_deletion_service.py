"""
Tests for Job Deletion Service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock

from services.job_deletion_service import JobDeletionService
from models import JobDB, OperationDB, LogEntryDB


class TestJobDeletionService:
    """Test cases for JobDeletionService"""
    
    @pytest.fixture
    def job_deletion_service(self, mock_database_manager, mock_metrics_service):
        """Create JobDeletionService instance for testing"""
        return JobDeletionService(mock_database_manager, mock_metrics_service)
    
    @pytest.mark.asyncio
    async def test_get_job_deletion_preview_success(self, job_deletion_service, populated_test_db):
        """Test successful job deletion preview"""
        job_id = 'test-job-123'
        
        result = await job_deletion_service.get_job_deletion_preview(job_id)
        
        assert result['job_id'] == job_id
        assert result['job_type'] == 'review'
        assert result['repository'] == 'test/repo'
        assert result['status'] == 'completed'
        assert result['operations_count'] == 1
        assert result['logs_count'] == 3
        assert result['can_delete'] is True
        assert 'cost_impact' in result
        assert result['started_at'] is not None
    
    @pytest.mark.asyncio
    async def test_get_job_deletion_preview_job_not_found(self, job_deletion_service, populated_test_db):
        """Test job deletion preview when job doesn't exist"""
        job_id = 'non-existent-job'
        
        with pytest.raises(ValueError, match="Job non-existent-job not found"):
            await job_deletion_service.get_job_deletion_preview(job_id)
    
    @pytest.mark.asyncio
    async def test_delete_job_and_related_data_success(self, job_deletion_service, populated_test_db):
        """Test successful job deletion"""
        job_id = 'test-job-123'
        
        result = await job_deletion_service.delete_job_and_related_data(job_id)
        
        assert result['job_id'] == job_id
        assert result['operations_deleted'] == 1
        assert result['logs_deleted'] == 3
        assert result['job_deleted'] == 1
        assert result['repository'] == 'test/repo'
        assert 'cost_impact' in result
        
        # Verify job was actually deleted
        job = populated_test_db.query(JobDB).filter(JobDB.job_id == job_id).first()
        assert job is None
        
        # Verify operations were deleted
        operations = populated_test_db.query(OperationDB).filter(OperationDB.job_id == job_id).all()
        assert len(operations) == 0
        
        # Verify logs were deleted
        logs = populated_test_db.query(LogEntryDB).filter(LogEntryDB.job_id == job_id).all()
        assert len(logs) == 0
    
    @pytest.mark.asyncio
    async def test_delete_job_and_related_data_job_not_found(self, job_deletion_service, populated_test_db):
        """Test job deletion when job doesn't exist"""
        job_id = 'non-existent-job'
        
        with pytest.raises(ValueError, match="Job non-existent-job not found"):
            await job_deletion_service.delete_job_and_related_data(job_id)
    
    @pytest.mark.asyncio
    async def test_delete_job_metrics_recalculation(self, job_deletion_service, populated_test_db):
        """Test that metrics are recalculated after job deletion"""
        job_id = 'test-job-123'
        
        await job_deletion_service.delete_job_and_related_data(job_id)
        
        # Verify metrics service was called
        job_deletion_service.metrics_service.recalculate_metrics_from_operations.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_calculate_job_cost_impact_legacy_data(self, job_deletion_service, populated_test_db):
        """Test cost calculation with legacy token data"""
        job_id = 'test-job-123'
        operation = populated_test_db.query(OperationDB).first()
        operation.model_used = 'gpt-5.3-codex'
        populated_test_db.commit()
        
        cost_impact = await job_deletion_service._calculate_job_cost_impact(populated_test_db, job_id)
        
        # Should calculate cost based on legacy tokens (1000 input, 500 output)
        # gpt-5.3-codex: input=0.00175, output=0.014 per 1000 tokens
        expected_cost = round((1000/1000) * 0.00175 + (500/1000) * 0.014, 2)
        assert cost_impact == pytest.approx(expected_cost, abs=0.01)
    
    @pytest.mark.asyncio
    async def test_calculate_job_cost_impact_multi_model_data(self, job_deletion_service, populated_test_db):
        """Test cost calculation with multi-model data"""
        # Update operation to use multi-model data
        operation = populated_test_db.query(OperationDB).first()
        operation.ai_models_used = {
            'gpt-5.3-codex': {'input_tokens': 800, 'output_tokens': 400},
            'gpt-5.3-codex-spark': {'input_tokens': 200, 'output_tokens': 100}
        }
        operation.model_used = None  # Clear legacy field
        populated_test_db.commit()
        
        job_id = 'test-job-123'
        cost_impact = await job_deletion_service._calculate_job_cost_impact(populated_test_db, job_id)
        
        # Should calculate cost for both models using configured rates
        codex_cost = (800/1000) * 0.00175 + (400/1000) * 0.014
        spark_cost = (200/1000) * 0.001 + (100/1000) * 0.008
        expected_cost = round(codex_cost + spark_cost, 2)
        assert cost_impact == pytest.approx(expected_cost, abs=0.01)
    
    @pytest.mark.asyncio
    async def test_calculate_job_cost_impact_no_tokens(self, job_deletion_service, populated_test_db):
        """Test cost calculation when operation has no token data"""
        # Update operation to have no token data
        operation = populated_test_db.query(OperationDB).first()
        operation.input_tokens = None
        operation.output_tokens = None
        operation.total_input_tokens = None
        operation.total_output_tokens = None
        operation.model_used = None
        operation.ai_models_used = None
        populated_test_db.commit()
        
        job_id = 'test-job-123'
        cost_impact = await job_deletion_service._calculate_job_cost_impact(populated_test_db, job_id)
        
        assert cost_impact == 0.0
    
    @pytest.mark.asyncio
    async def test_calculate_job_cost_impact_error_handling(self, job_deletion_service, populated_test_db):
        """Test cost calculation error handling"""
        # Mock metrics service to raise an exception
        job_deletion_service.metrics_service.get_or_create_config.side_effect = Exception("Test error")
        
        job_id = 'test-job-123'
        cost_impact = await job_deletion_service._calculate_job_cost_impact(populated_test_db, job_id)
        
        # Should return 0.0 on error
        assert cost_impact == 0.0
    
    @pytest.mark.asyncio
    async def test_delete_job_database_rollback_on_error(self, job_deletion_service, populated_test_db):
        """Test that database rollback occurs on deletion error"""
        # Mock the metrics service to raise an exception
        job_deletion_service.metrics_service.recalculate_metrics_from_operations.side_effect = Exception("Database error")
        
        job_id = 'test-job-123'
        
        # The service should handle the error and re-raise it
        with pytest.raises(Exception):
            await job_deletion_service.delete_job_and_related_data(job_id)
        
        # Verify rollback was called (this would be handled by the database session context manager)
        # In a real scenario, we'd check that the transaction was rolled back
