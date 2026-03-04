"""
Integration tests for job deletion API endpoints.
Uses conftest client_app and auth_headers; patches JobDeletionService.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestJobDeletionAPI:
    """Test cases for job deletion API endpoints"""

    def test_get_job_deletion_preview_success(self, client_app, auth_headers):
        """Test successful job deletion preview API call"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.get_job_deletion_preview = AsyncMock(return_value={
                'job_id': 'test-job-123',
                'job_type': 'review',
                'repository': 'test/repo',
                'status': 'completed',
                'started_at': '2024-01-15T10:00:00',
                'operations_count': 5,
                'logs_count': 12,
                'cost_impact': 25.50,
                'can_delete': True
            })
            mock_service_class.return_value = mock_service

            response = client_app.get('/api/jobs/test-job-123/deletion-preview', headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data['data']['job_id'] == 'test-job-123'
            assert data['data']['operations_count'] == 5
            assert data['data']['logs_count'] == 12
            assert data['data']['cost_impact'] == 25.50

    def test_get_job_deletion_preview_job_not_found(self, client_app, auth_headers):
        """Test job deletion preview when job doesn't exist"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.get_job_deletion_preview = AsyncMock(side_effect=ValueError("Job test-job-999 not found"))
            mock_service_class.return_value = mock_service

            response = client_app.get('/api/jobs/test-job-999/deletion-preview', headers=auth_headers)

            assert response.status_code == 404
            assert 'Job test-job-999 not found' in response.json()['detail']

    def test_get_job_deletion_preview_service_error(self, client_app, auth_headers):
        """Test job deletion preview when service raises an error"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.get_job_deletion_preview = AsyncMock(side_effect=Exception("Database error"))
            mock_service_class.return_value = mock_service

            response = client_app.get('/api/jobs/test-job-123/deletion-preview', headers=auth_headers)

            assert response.status_code == 500
            assert 'Failed to get deletion preview' in response.json()['detail']

    def test_delete_job_success(self, client_app, auth_headers):
        """Test successful job deletion API call"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.delete_job_and_related_data = AsyncMock(return_value={
                'job_id': 'test-job-123',
                'operations_deleted': 5,
                'logs_deleted': 12,
                'job_deleted': 1,
                'cost_impact': 25.50,
                'repository': 'test/repo'
            })
            mock_service_class.return_value = mock_service

            response = client_app.delete('/api/jobs/test-job-123', headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data['data']['job_id'] == 'test-job-123'
            assert data['data']['operations_deleted'] == 5
            assert data['data']['logs_deleted'] == 12
            assert data['data']['job_deleted'] == 1
            assert data['message'] == "Job and related data deleted successfully"

    def test_delete_job_not_found(self, client_app, auth_headers):
        """Test job deletion when job doesn't exist"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.delete_job_and_related_data = AsyncMock(side_effect=ValueError("Job test-job-999 not found"))
            mock_service_class.return_value = mock_service

            response = client_app.delete('/api/jobs/test-job-999', headers=auth_headers)

            assert response.status_code == 404
            assert 'Job test-job-999 not found' in response.json()['detail']

    def test_delete_job_service_error(self, client_app, auth_headers):
        """Test job deletion when service raises an error"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.delete_job_and_related_data = AsyncMock(side_effect=Exception("Database error"))
            mock_service_class.return_value = mock_service

            response = client_app.delete('/api/jobs/test-job-123', headers=auth_headers)

            assert response.status_code == 500
            assert 'Failed to delete job' in response.json()['detail']

    def test_delete_job_metrics_recalculation(self, client_app, auth_headers):
        """Test that metrics are recalculated after job deletion"""
        with patch('services.job_deletion_service.JobDeletionService') as mock_service_class:
            mock_service = Mock()
            mock_service.delete_job_and_related_data = AsyncMock(return_value={
                'job_id': 'test-job-123',
                'operations_deleted': 5,
                'logs_deleted': 12,
                'job_deleted': 1,
                'cost_impact': 25.50,
                'repository': 'test/repo'
            })
            mock_service_class.return_value = mock_service

            response = client_app.delete('/api/jobs/test-job-123', headers=auth_headers)

            assert response.status_code == 200
