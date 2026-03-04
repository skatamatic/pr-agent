"""
Integration tests for cleanup API endpoints.
Uses conftest client_app and auth_headers; patches DataCleanupService.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch


class TestCleanupAPI:
    """Test cases for cleanup API endpoints"""

    def test_preview_cleanup_success(self, client_app, auth_headers):
        """Test successful cleanup preview API call"""
        with patch('services.data_cleanup_service.DataCleanupService') as mock_service_class:
            mock_service = Mock()
            mock_service.get_cleanup_preview = AsyncMock(return_value={
                'cutoff_date': '2024-01-15T10:00:00',
                'repository': None,
                'before_cleanup': {
                    'operations': 100,
                    'jobs': 50,
                    'logs': 500,
                    'notification_events': 25,
                    'cost_savings': 1000.0
                },
                'after_cleanup': {
                    'operations': 80,
                    'jobs': 40,
                    'logs': 400,
                    'notification_events': 20,
                    'cost_savings': 800.0
                },
                'to_be_deleted': {
                    'operations': 20,
                    'jobs': 10,
                    'logs': 100,
                    'notification_events': 5
                },
                'cost_impact': -200.0,
                'storage_impact_mb': 15.5
            })
            mock_service_class.return_value = mock_service

            request_data = {
                'cutoff_date': '2024-01-15T10:00:00Z',
                'repository': None
            }

            response = client_app.post('/api/admin/cleanup/preview', json=request_data, headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data['data']['cutoff_date'] == '2024-01-15T10:00:00'
            assert data['data']['before_cleanup']['operations'] == 100
            assert data['data']['to_be_deleted']['operations'] == 20

    def test_preview_cleanup_missing_cutoff_date(self, client_app, auth_headers):
        """Test cleanup preview with missing cutoff_date"""
        request_data = {
            'repository': None
        }

        response = client_app.post('/api/admin/cleanup/preview', json=request_data, headers=auth_headers)

        assert response.status_code == 400
        assert 'cutoff_date' in response.json()['detail'].lower()

    def test_preview_cleanup_invalid_date_format(self, client_app, auth_headers):
        """Test cleanup preview with invalid date format"""
        request_data = {
            'cutoff_date': 'invalid-date',
            'repository': None
        }

        response = client_app.post('/api/admin/cleanup/preview', json=request_data, headers=auth_headers)

        assert response.status_code == 400
        assert 'cutoff_date' in response.json()['detail'].lower() or 'invalid' in response.json()['detail'].lower()

    def test_preview_cleanup_with_repository(self, client_app, auth_headers):
        """Test cleanup preview with specific repository"""
        with patch('services.data_cleanup_service.DataCleanupService') as mock_service_class:
            mock_service = Mock()
            mock_service.get_cleanup_preview = AsyncMock(return_value={
                'cutoff_date': '2024-01-15T10:00:00',
                'repository': 'test/repo',
                'before_cleanup': {'operations': 50, 'jobs': 25, 'logs': 250, 'notification_events': 12, 'cost_savings': 500.0},
                'after_cleanup': {'operations': 40, 'jobs': 20, 'logs': 200, 'notification_events': 10, 'cost_savings': 400.0},
                'to_be_deleted': {'operations': 10, 'jobs': 5, 'logs': 50, 'notification_events': 2},
                'cost_impact': -100.0,
                'storage_impact_mb': 7.5
            })
            mock_service_class.return_value = mock_service

            request_data = {
                'cutoff_date': '2024-01-15T10:00:00Z',
                'repository': 'test/repo'
            }

            response = client_app.post('/api/admin/cleanup/preview', json=request_data, headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data['data']['repository'] == 'test/repo'

    def test_execute_cleanup_success(self, client_app, auth_headers):
        """Test successful cleanup execution API call"""
        with patch('services.data_cleanup_service.DataCleanupService') as mock_service_class:
            mock_service = Mock()
            mock_service.execute_cleanup = AsyncMock(return_value={
                'cutoff_date': '2024-01-15T10:00:00',
                'repository': None,
                'deleted_counts': {
                    'operations': 20,
                    'jobs': 10,
                    'logs': 100,
                    'notification_events': 5
                },
                'backup_path': '/tmp/test_backup.db.gz'
            })
            mock_service_class.return_value = mock_service

            request_data = {
                'cutoff_date': '2024-01-15T10:00:00Z',
                'repository': None,
                'data_types': ['operations', 'jobs', 'logs', 'notification_events']
            }

            response = client_app.post('/api/admin/cleanup/execute', json=request_data, headers=auth_headers)

            assert response.status_code == 200
            data = response.json()
            assert data['data']['deleted_counts']['operations'] == 20
            assert 'cleanup' in data.get('message', '').lower() or 'data' in data.get('message', '').lower()

    def test_execute_cleanup_missing_cutoff_date(self, client_app, auth_headers):
        """Test cleanup execution with missing cutoff_date"""
        request_data = {
            'repository': None,
            'data_types': ['operations']
        }

        response = client_app.post('/api/admin/cleanup/execute', json=request_data, headers=auth_headers)

        assert response.status_code == 400
        assert 'cutoff_date' in response.json()['detail'].lower()

    def test_execute_cleanup_invalid_date_format(self, client_app, auth_headers):
        """Test cleanup execution with invalid date format"""
        request_data = {
            'cutoff_date': 'not-a-date',
            'repository': None,
            'data_types': ['operations']
        }

        response = client_app.post('/api/admin/cleanup/execute', json=request_data, headers=auth_headers)

        assert response.status_code == 400
        assert 'cutoff_date' in response.json()['detail'].lower() or 'invalid' in response.json()['detail'].lower()

    def test_execute_cleanup_default_data_types(self, client_app, auth_headers):
        """Test cleanup execution with default data types"""
        with patch('services.data_cleanup_service.DataCleanupService') as mock_service_class:
            mock_service = Mock()
            mock_service.execute_cleanup = AsyncMock(return_value={
                'cutoff_date': '2024-01-15T10:00:00',
                'repository': None,
                'deleted_counts': {'operations': 20, 'jobs': 10, 'logs': 100, 'notification_events': 5},
                'backup_path': '/tmp/test_backup.db.gz'
            })
            mock_service_class.return_value = mock_service

            request_data = {
                'cutoff_date': '2024-01-15T10:00:00Z',
                'repository': None
            }

            response = client_app.post('/api/admin/cleanup/execute', json=request_data, headers=auth_headers)

            assert response.status_code == 200
            mock_service.execute_cleanup.assert_called_once()

    def test_preview_cleanup_service_error(self, client_app, auth_headers):
        """Test cleanup preview when service raises an error"""
        with patch('services.data_cleanup_service.DataCleanupService') as mock_service_class:
            mock_service = Mock()
            mock_service.get_cleanup_preview = AsyncMock(side_effect=Exception("Service error"))
            mock_service_class.return_value = mock_service

            request_data = {
                'cutoff_date': '2024-01-15T10:00:00Z',
                'repository': None
            }

            response = client_app.post('/api/admin/cleanup/preview', json=request_data, headers=auth_headers)

            assert response.status_code == 500
            assert 'preview' in response.json()['detail'].lower() or 'fail' in response.json()['detail'].lower()

    def test_execute_cleanup_service_error(self, client_app, auth_headers):
        """Test cleanup execution when service raises an error"""
        with patch('services.data_cleanup_service.DataCleanupService') as mock_service_class:
            mock_service = Mock()
            mock_service.execute_cleanup = AsyncMock(side_effect=Exception("Service error"))
            mock_service_class.return_value = mock_service

            request_data = {
                'cutoff_date': '2024-01-15T10:00:00Z',
                'repository': None,
                'data_types': ['operations']
            }

            response = client_app.post('/api/admin/cleanup/execute', json=request_data, headers=auth_headers)

            assert response.status_code == 500
            assert 'cleanup' in response.json()['detail'].lower() or 'fail' in response.json()['detail'].lower()
