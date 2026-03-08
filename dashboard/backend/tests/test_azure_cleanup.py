"""
Tests for Azure DevOps resource cleanup paths.

Covers:
  - cleanup_azure_resources orchestrator
  - delete_pipeline_definition
  - Repo deletion triggering Azure cleanup
  - Runner connection deletion triggering Azure cleanup
  - Edge cases: missing PAT, non-Azure provider, partial failures
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.azure_pipeline_config_service import AzurePipelineConfigService


@pytest.fixture
def svc():
    return AzurePipelineConfigService()


@pytest.fixture
def azure_repo_data():
    return {
        'provider': 'azure_devops',
        'url': 'https://dev.azure.com/myorg/myproject/_git/myrepo',
        'azure_pat': 'test-pat-token',
        'id': 42,
    }


# ──────────────────────────────────────────────────────────────
#  cleanup_azure_resources
# ──────────────────────────────────────────────────────────────

class TestCleanupAzureResources:

    @pytest.mark.asyncio
    async def test_skips_non_azure_provider(self, svc):
        result = await svc.cleanup_azure_resources(
            {'provider': 'github', 'url': 'https://github.com/foo/bar', 'azure_pat': 'x'}
        )
        assert result['skipped'] is True
        assert 'Not an Azure DevOps' in result['reason']

    @pytest.mark.asyncio
    async def test_skips_missing_pat(self, svc):
        result = await svc.cleanup_azure_resources(
            {'provider': 'azure_devops', 'url': 'https://dev.azure.com/org/proj/_git/repo', 'azure_pat': ''}
        )
        assert result['skipped'] is True
        assert 'PAT' in result['reason']

    @pytest.mark.asyncio
    async def test_skips_whitespace_pat(self, svc):
        result = await svc.cleanup_azure_resources(
            {'provider': 'azure_devops', 'url': 'https://dev.azure.com/org/proj/_git/repo', 'azure_pat': '   '}
        )
        assert result['skipped'] is True

    @pytest.mark.asyncio
    async def test_skips_bad_url(self, svc):
        result = await svc.cleanup_azure_resources(
            {'provider': 'azure_devops', 'url': 'not-a-url', 'azure_pat': 'tok'}
        )
        assert result['skipped'] is True

    @pytest.mark.asyncio
    async def test_removes_policies_and_pipelines(self, svc, azure_repo_data):
        """Full happy path: list_build_policies returns 2 policies, _check_pipeline_definitions returns 1 PR-Agent pipeline."""
        svc.list_build_policies = AsyncMock(return_value={
            'policies': [
                {'policy_id': 10, 'pipeline_name': 'PR-Agent Review (master)'},
                {'policy_id': 11, 'pipeline_name': 'PR-Agent Review (develop)'},
            ]
        })
        svc.delete_build_policy = AsyncMock(return_value={'success': True})
        svc._check_pipeline_definitions = AsyncMock(return_value={
            'has_pipelines': True,
            'pipelines': [
                {'id': 100, 'name': 'PR-Agent (myrepo)'},
                {'id': 200, 'name': 'Other Build'},
            ]
        })
        svc.delete_pipeline_definition = AsyncMock(return_value={'success': True})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert svc.delete_build_policy.call_count == 2
        assert svc.delete_pipeline_definition.call_count == 1  # only PR-Agent pipeline
        assert 10 in result['policies_removed']
        assert 11 in result['policies_removed']
        assert 100 in result['pipelines_removed']
        assert 200 not in result['pipelines_removed']
        assert len(result['policies_failed']) == 0
        assert len(result['pipelines_failed']) == 0
        assert 'Removed 3' in result['summary']

    @pytest.mark.asyncio
    async def test_skips_non_pr_agent_policies(self, svc, azure_repo_data):
        """Only policies named 'PR-Agent*' should be deleted."""
        svc.list_build_policies = AsyncMock(return_value={
            'policies': [
                {'policy_id': 10, 'pipeline_name': 'PR-Agent Review (master)'},
                {'policy_id': 11, 'pipeline_name': 'Build validation'},
                {'policy_id': 12, 'pipeline_name': None},
                {'policy_id': 13, 'pipeline_name': 'pr-agent (develop)'},
            ]
        })
        svc.delete_build_policy = AsyncMock(return_value={'success': True})
        svc._check_pipeline_definitions = AsyncMock(return_value={'has_pipelines': False, 'pipelines': []})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert svc.delete_build_policy.call_count == 2
        assert 10 in result['policies_removed']
        assert 13 in result['policies_removed']
        assert 11 not in result['policies_removed']
        assert 12 not in result['policies_removed']

    @pytest.mark.asyncio
    async def test_continues_on_policy_delete_failure(self, svc, azure_repo_data):
        """If one policy delete fails, the rest still get attempted."""
        svc.list_build_policies = AsyncMock(return_value={
            'policies': [
                {'policy_id': 10, 'pipeline_name': 'PR-Agent Review (master)'},
                {'policy_id': 11, 'pipeline_name': 'PR-Agent Review (develop)'},
            ]
        })
        svc.delete_build_policy = AsyncMock(side_effect=[
            {'success': False, 'error': 'API timeout'},
            {'success': True},
        ])
        svc._check_pipeline_definitions = AsyncMock(return_value={'has_pipelines': False, 'pipelines': []})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert svc.delete_build_policy.call_count == 2
        assert len(result['policies_removed']) == 1
        assert len(result['policies_failed']) == 1
        assert result['policies_failed'][0]['policy_id'] == 10

    @pytest.mark.asyncio
    async def test_continues_on_policy_delete_exception(self, svc, azure_repo_data):
        """If policy delete raises, we catch and keep going."""
        svc.list_build_policies = AsyncMock(return_value={
            'policies': [
                {'policy_id': 10, 'pipeline_name': 'PR-Agent Review (master)'},
                {'policy_id': 11, 'pipeline_name': 'PR-Agent Review (develop)'},
            ]
        })
        svc.delete_build_policy = AsyncMock(side_effect=[
            Exception('network error'),
            {'success': True},
        ])
        svc._check_pipeline_definitions = AsyncMock(return_value={'has_pipelines': False, 'pipelines': []})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert len(result['policies_removed']) == 1
        assert len(result['policies_failed']) == 1
        assert 'network error' in result['policies_failed'][0]['error']

    @pytest.mark.asyncio
    async def test_continues_on_pipeline_delete_failure(self, svc, azure_repo_data):
        svc.list_build_policies = AsyncMock(return_value={'policies': []})
        svc._check_pipeline_definitions = AsyncMock(return_value={
            'has_pipelines': True,
            'pipelines': [
                {'id': 100, 'name': 'PR-Agent (myrepo)'},
            ]
        })
        svc.delete_pipeline_definition = AsyncMock(return_value={'success': False, 'error': 'Permission denied'})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert len(result['pipelines_failed']) == 1
        assert result['pipelines_failed'][0]['pipeline_id'] == 100

    @pytest.mark.asyncio
    async def test_handles_policy_list_error(self, svc, azure_repo_data):
        """If listing policies returns an error, it's recorded but doesn't crash."""
        svc.list_build_policies = AsyncMock(return_value={'error': 'Auth failed'})
        svc._check_pipeline_definitions = AsyncMock(return_value={'has_pipelines': False, 'pipelines': []})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert len(result['errors']) == 1
        assert 'Could not list policies' in result['errors'][0]

    @pytest.mark.asyncio
    async def test_handles_policy_list_exception(self, svc, azure_repo_data):
        """If listing policies throws, it's caught."""
        svc.list_build_policies = AsyncMock(side_effect=Exception('connection refused'))
        svc._check_pipeline_definitions = AsyncMock(return_value={'has_pipelines': False, 'pipelines': []})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert len(result['errors']) >= 1

    @pytest.mark.asyncio
    async def test_handles_pipeline_list_exception(self, svc, azure_repo_data):
        svc.list_build_policies = AsyncMock(return_value={'policies': []})
        svc._check_pipeline_definitions = AsyncMock(side_effect=Exception('timeout'))

        result = await svc.cleanup_azure_resources(azure_repo_data)

        assert len(result['errors']) >= 1
        assert 'Pipeline cleanup error' in result['errors'][0]

    @pytest.mark.asyncio
    async def test_skips_non_pr_agent_pipelines(self, svc, azure_repo_data):
        """Only pipelines named 'PR-Agent*' should be deleted."""
        svc.list_build_policies = AsyncMock(return_value={'policies': []})
        svc._check_pipeline_definitions = AsyncMock(return_value={
            'has_pipelines': True,
            'pipelines': [
                {'id': 100, 'name': 'Build Main'},
                {'id': 101, 'name': 'Deploy Staging'},
                {'id': 102, 'name': 'pr-agent (myrepo)'},
            ]
        })
        svc.delete_pipeline_definition = AsyncMock(return_value={'success': True})

        result = await svc.cleanup_azure_resources(azure_repo_data)

        svc.delete_pipeline_definition.assert_called_once()
        assert 102 in result['pipelines_removed']
        assert 100 not in result['pipelines_removed']
        assert 101 not in result['pipelines_removed']

    @pytest.mark.asyncio
    async def test_respects_remove_policies_false(self, svc, azure_repo_data):
        svc.list_build_policies = AsyncMock(return_value={'policies': [{'policy_id': 1, 'pipeline_name': 'x'}]})
        svc.delete_build_policy = AsyncMock(return_value={'success': True})
        svc._check_pipeline_definitions = AsyncMock(return_value={'has_pipelines': False, 'pipelines': []})

        result = await svc.cleanup_azure_resources(azure_repo_data, remove_policies=False)

        svc.list_build_policies.assert_not_called()
        assert len(result['policies_removed']) == 0

    @pytest.mark.asyncio
    async def test_respects_remove_pipelines_false(self, svc, azure_repo_data):
        svc.list_build_policies = AsyncMock(return_value={'policies': []})
        svc._check_pipeline_definitions = AsyncMock(return_value={
            'has_pipelines': True,
            'pipelines': [{'id': 1, 'name': 'PR-Agent (x)'}],
        })
        svc.delete_pipeline_definition = AsyncMock(return_value={'success': True})

        result = await svc.cleanup_azure_resources(azure_repo_data, remove_pipelines=False)

        svc._check_pipeline_definitions.assert_not_called()
        assert len(result['pipelines_removed']) == 0


# ──────────────────────────────────────────────────────────────
#  delete_pipeline_definition
# ──────────────────────────────────────────────────────────────

class TestDeletePipelineDefinition:

    @pytest.mark.asyncio
    async def test_missing_pat(self, svc):
        result = await svc.delete_pipeline_definition(
            {'provider': 'azure_devops', 'url': 'https://dev.azure.com/o/p/_git/r', 'azure_pat': ''}, 1
        )
        assert not result['success']
        assert 'PAT' in result['error']

    @pytest.mark.asyncio
    async def test_bad_url(self, svc):
        result = await svc.delete_pipeline_definition(
            {'provider': 'azure_devops', 'url': 'bad', 'azure_pat': 'tok'}, 1
        )
        assert not result['success']

    @pytest.mark.asyncio
    async def test_success_204(self, svc, azure_repo_data):
        mock_resp = AsyncMock()
        mock_resp.status = 204
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.delete = MagicMock(return_value=mock_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await svc.delete_pipeline_definition(azure_repo_data, 123)

        assert result['success']

    @pytest.mark.asyncio
    async def test_already_deleted_404(self, svc, azure_repo_data):
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session.delete = MagicMock(return_value=mock_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await svc.delete_pipeline_definition(azure_repo_data, 123)

        assert result['success']
        assert 'already deleted' in result.get('message', '')


# ──────────────────────────────────────────────────────────────
#  Repo deletion endpoint triggers cleanup
# ──────────────────────────────────────────────────────────────

class TestRepoDeleteTriggersCleanup:

    def test_delete_azure_repo_triggers_cleanup(self, client_app, auth_headers):
        """Create an Azure DevOps repo, delete it, and verify cleanup was attempted."""
        # Create repo
        resp = client_app.post("/api/repositories", json={
            "name": "CleanupTest",
            "provider": "azure_devops",
            "url": "https://dev.azure.com/testorg/testproject/_git/cleanuptest",
            "azure_pat": "test-pat-value",
            "is_active": True,
        }, headers=auth_headers)
        assert resp.status_code == 200
        repo_id = resp.json()["data"]["id"]

        with patch(
            'services.azure_pipeline_config_service.AzurePipelineConfigService.cleanup_azure_resources',
            new_callable=AsyncMock,
            return_value={'summary': 'Removed 2 resource(s)', 'policies_removed': [1, 2], 'pipelines_removed': [],
                         'policies_failed': [], 'pipelines_failed': [], 'errors': [], 'yaml_removed': False},
        ) as mock_cleanup:
            resp = client_app.delete(f"/api/repositories/{repo_id}", headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["deleted"] is True
            assert data["azure_cleanup"]["summary"] == "Removed 2 resource(s)"
            mock_cleanup.assert_called_once()

    def test_delete_github_repo_skips_cleanup(self, client_app, auth_headers):
        """GitHub repos should not trigger Azure cleanup."""
        resp = client_app.post("/api/repositories", json={
            "name": "GitHubCleanupTest",
            "provider": "github",
            "url": "https://github.com/test/repo",
            "is_active": True,
        }, headers=auth_headers)
        assert resp.status_code == 200
        repo_id = resp.json()["data"]["id"]

        with patch(
            'services.azure_pipeline_config_service.AzurePipelineConfigService.cleanup_azure_resources',
            new_callable=AsyncMock,
        ) as mock_cleanup:
            resp = client_app.delete(f"/api/repositories/{repo_id}", headers=auth_headers)
            assert resp.status_code == 200
            mock_cleanup.assert_not_called()

    def test_delete_repo_succeeds_even_if_cleanup_fails(self, client_app, auth_headers):
        """If Azure cleanup throws, the repo should still be deleted."""
        resp = client_app.post("/api/repositories", json={
            "name": "CleanupFailTest",
            "provider": "azure_devops",
            "url": "https://dev.azure.com/testorg/testproject/_git/failtest",
            "azure_pat": "test-pat",
            "is_active": True,
        }, headers=auth_headers)
        assert resp.status_code == 200
        repo_id = resp.json()["data"]["id"]

        with patch(
            'services.azure_pipeline_config_service.AzurePipelineConfigService.cleanup_azure_resources',
            new_callable=AsyncMock,
            side_effect=Exception('Network error'),
        ):
            resp = client_app.delete(f"/api/repositories/{repo_id}", headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["data"]["deleted"] is True

        # Verify repo is actually gone
        resp = client_app.get(f"/api/repositories/{repo_id}", headers=auth_headers)
        assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
#  Azure cleanup endpoint
# ──────────────────────────────────────────────────────────────

class TestAzureCleanupEndpoint:

    def test_cleanup_endpoint_non_azure_repo(self, client_app, auth_headers):
        resp = client_app.post("/api/repositories", json={
            "name": "GitHubForCleanup",
            "provider": "github",
            "url": "https://github.com/test/repo",
            "is_active": True,
        }, headers=auth_headers)
        repo_id = resp.json()["data"]["id"]

        resp = client_app.post(f"/api/repositories/{repo_id}/azure-cleanup", headers=auth_headers)
        assert resp.status_code == 400

    def test_cleanup_endpoint_missing_pat(self, client_app, auth_headers):
        resp = client_app.post("/api/repositories", json={
            "name": "AzureNoPat",
            "provider": "azure_devops",
            "url": "https://dev.azure.com/o/p/_git/r",
            "is_active": True,
        }, headers=auth_headers)
        repo_id = resp.json()["data"]["id"]

        resp = client_app.post(f"/api/repositories/{repo_id}/azure-cleanup", headers=auth_headers)
        assert resp.status_code == 400
        assert 'PAT' in resp.json()["detail"]

    def test_cleanup_endpoint_success(self, client_app, auth_headers):
        resp = client_app.post("/api/repositories", json={
            "name": "AzureCleanupTarget",
            "provider": "azure_devops",
            "url": "https://dev.azure.com/o/p/_git/r",
            "azure_pat": "valid-pat",
            "is_active": True,
        }, headers=auth_headers)
        repo_id = resp.json()["data"]["id"]

        with patch(
            'services.azure_pipeline_config_service.AzurePipelineConfigService.cleanup_azure_resources',
            new_callable=AsyncMock,
            return_value={
                'summary': 'Removed 1 resource(s)',
                'policies_removed': [10], 'pipelines_removed': [],
                'policies_failed': [], 'pipelines_failed': [],
                'errors': [], 'yaml_removed': False,
            },
        ) as mock_cleanup:
            resp = client_app.post(f"/api/repositories/{repo_id}/azure-cleanup", headers=auth_headers)
            assert resp.status_code == 200
            assert 'Removed 1' in resp.json()["message"]
            mock_cleanup.assert_called_once()

    def test_cleanup_endpoint_not_found(self, client_app, auth_headers):
        resp = client_app.post("/api/repositories/99999/azure-cleanup", headers=auth_headers)
        assert resp.status_code == 404

    def test_cleanup_endpoint_requires_auth(self, client_app):
        resp = client_app.post("/api/repositories/1/azure-cleanup")
        assert resp.status_code in (401, 403)
