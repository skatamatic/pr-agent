"""
Unit tests for pr_agent.algo.csharp_context_client.

Ensures login never logs credentials and covers login success/failure paths.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from pr_agent.algo import csharp_context_client


def _run(coro):
    """Run async function in sync test."""
    return asyncio.run(coro)


class TestLoginAndGetServiceToken:
    """Tests for _login_and_get_service_token."""

    def test_credentials_never_logged(self):
        """Ensure username/password are never passed to logger (security)."""
        mock_logger = MagicMock()
        service_settings = MagicMock()
        service_settings.base_url = "http://localhost:7110"
        service_settings.get = lambda k, default=None: {
            "base_url": "http://localhost:7110",
            "username": "secret_user",
            "password": "secret_pass",
        }.get(k, default)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"token": "abc123"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(csharp_context_client, "get_logger", return_value=mock_logger):
            result = _run(
                csharp_context_client._login_and_get_service_token(mock_client, service_settings)
            )

        assert result == "abc123"
        # No log call must contain credentials
        for call in mock_logger.method_calls:
            name = call[0]
            args = str(call[1])
            kwargs = str(call[2])
            combined = args + kwargs
            assert "secret_user" not in combined, f"Username leaked in logger.{name}"
            assert "secret_pass" not in combined, f"Password leaked in logger.{name}"
            assert "Password" not in combined or "not configured" in combined
            assert "Username" not in combined or "not configured" in combined

    def test_returns_none_when_username_missing(self):
        """When username is missing, returns None and does not call HTTP."""
        service_settings = MagicMock()
        service_settings.base_url = "http://localhost:7110"
        service_settings.get = lambda k, default=None: {"base_url": "http://localhost:7110", "username": None, "password": "p"}.get(k, default)
        mock_client = MagicMock(spec=httpx.AsyncClient)

        with patch.object(csharp_context_client, "get_logger", return_value=MagicMock()):
            result = _run(
                csharp_context_client._login_and_get_service_token(mock_client, service_settings)
            )

        assert result is None
        mock_client.post.assert_not_called()

    def test_returns_none_when_password_missing(self):
        """When password is missing, returns None and does not call HTTP."""
        service_settings = MagicMock()
        service_settings.base_url = "http://localhost:7110"
        service_settings.get = lambda k, default=None: {"base_url": "http://localhost:7110", "username": "u", "password": None}.get(k, default)
        mock_client = MagicMock(spec=httpx.AsyncClient)

        with patch.object(csharp_context_client, "get_logger", return_value=MagicMock()):
            result = _run(
                csharp_context_client._login_and_get_service_token(mock_client, service_settings)
            )

        assert result is None
        mock_client.post.assert_not_called()

    def test_returns_token_on_success(self):
        """On 200 with token in body, returns the token."""
        service_settings = MagicMock()
        service_settings.base_url = "http://localhost:7110"
        service_settings.get = lambda k, default=None: {"base_url": "http://localhost:7110", "username": "u", "password": "p"}.get(k, default)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"token": "jwt-here"})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(csharp_context_client, "get_logger", return_value=MagicMock()):
            result = _run(
                csharp_context_client._login_and_get_service_token(mock_client, service_settings)
            )

        assert result == "jwt-here"
        mock_client.post.assert_called_once()

    def test_returns_none_on_http_error(self):
        """On HTTP 401/5xx, returns None."""
        service_settings = MagicMock()
        service_settings.base_url = "http://localhost:7110"
        service_settings.get = lambda k, default=None: {"base_url": "http://localhost:7110", "username": "u", "password": "p"}.get(k, default)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client.post = AsyncMock(return_value=mock_response)

        def raise_status():
            raise httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)

        mock_response.raise_for_status = raise_status

        with patch.object(csharp_context_client, "get_logger", return_value=MagicMock()):
            result = _run(
                csharp_context_client._login_and_get_service_token(mock_client, service_settings)
            )

        assert result is None

    def test_returns_none_when_token_missing_in_response(self):
        """When response has no 'token' key, returns None."""
        service_settings = MagicMock()
        service_settings.base_url = "http://localhost:7110"
        service_settings.get = lambda k, default=None: {"base_url": "http://localhost:7110", "username": "u", "password": "p"}.get(k, default)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={})
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(csharp_context_client, "get_logger", return_value=MagicMock()):
            result = _run(
                csharp_context_client._login_and_get_service_token(mock_client, service_settings)
            )

        assert result is None


class TestBuildAnalysisPayload:
    """Tests for backward/forward-compatible analysis payload builder."""

    def test_payload_includes_new_and_legacy_fields(self):
        source_control_info = {
            "isGitHub": False,
            "token": "ado_pat",
            "org": "mdt-software",
            "owner": "mdt-software",
            "project": "Product",
            "repo": "Archive.MDT.ConfigEditor",
        }

        payload = csharp_context_client._build_analysis_payload(
            source_control_info=source_control_info,
            owner="Product",
            repo_name="Archive.MDT.ConfigEditor",
            pr_number=5214,
            access_token="ado_pat",
            depth=2,
            mode="Minified",
        )

        assert payload["sourceControlConnectionInfo"] == source_control_info
        assert payload["prNumber"] == 5214
        assert payload["depth"] == 2
        assert payload["mode"] == "Minified"
        # Legacy compatibility
        assert payload["token"] == "ado_pat"
        assert payload["owner"] == "Product"
        assert payload["repo"] == "Archive.MDT.ConfigEditor"

    def test_payload_falls_back_to_owner_arg_when_source_owner_missing(self):
        source_control_info = {
            "isGitHub": True,
            "token": "gh_pat",
            "org": "",
            "owner": "",
            "project": "",
            "repo": "repo",
        }

        payload = csharp_context_client._build_analysis_payload(
            source_control_info=source_control_info,
            owner="my-owner",
            repo_name="repo",
            pr_number=1,
            access_token="gh_pat",
            depth=1,
            mode="Minified",
        )

        assert payload["owner"] == "my-owner"


class TestResolveSourceControlType:
    def test_prefers_azure_config_value(self):
        settings = MagicMock()
        settings.config.get = lambda key, default=None: "azure"
        with patch.object(csharp_context_client, "get_settings", return_value=settings):
            with patch.dict("os.environ", {}, clear=False):
                assert csharp_context_client._resolve_source_control_type() == "azure"

    def test_detects_azure_from_pipeline_env_when_config_is_github(self):
        settings = MagicMock()
        settings.config.get = lambda key, default=None: "github"
        with patch.object(csharp_context_client, "get_settings", return_value=settings):
            with patch.dict("os.environ", {"SYSTEM_COLLECTIONURI": "https://mdt-software.visualstudio.com/"}):
                assert csharp_context_client._resolve_source_control_type() == "azure"

    def test_defaults_to_github_without_azure_signals(self):
        settings = MagicMock()
        settings.config.get = lambda key, default=None: "github"
        with patch.object(csharp_context_client, "get_settings", return_value=settings):
            with patch.dict("os.environ", {}, clear=True):
                assert csharp_context_client._resolve_source_control_type() == "github"


class TestNormalizeAzureOrgAndCollection:
    def test_visualstudio_collection_uri_parsing(self):
        org, uri = csharp_context_client._normalize_azure_org_and_collection(
            "https://mdt-software.visualstudio.com/"
        )
        assert org == "mdt-software"
        assert uri == "https://mdt-software.visualstudio.com"

    def test_dev_azure_collection_uri_parsing(self):
        org, uri = csharp_context_client._normalize_azure_org_and_collection(
            "https://dev.azure.com/mdt-software/"
        )
        assert org == "mdt-software"
        assert uri == "https://dev.azure.com/mdt-software"

    def test_plain_org_name_parsing(self):
        org, uri = csharp_context_client._normalize_azure_org_and_collection("mdt-software")
        assert org == "mdt-software"
        assert uri == "https://dev.azure.com/mdt-software"
