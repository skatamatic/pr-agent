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
