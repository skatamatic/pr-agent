"""
Unit tests for WebSocketManager.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from websocket_manager import WebSocketManager


class TestWebSocketManager:
    """WebSocketManager connect, disconnect, broadcast."""

    @pytest.fixture
    def manager(self):
        return WebSocketManager()

    @pytest.fixture
    def mock_ws(self):
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.client = ("127.0.0.1", 12345)
        ws.client_state = MagicMock()
        ws.client_state.value = 1  # CONNECTED
        return ws

    @pytest.mark.asyncio
    async def test_connect_accepts_and_sends_welcome(self, manager, mock_ws):
        await manager.connect(mock_ws)
        mock_ws.accept.assert_called_once()
        assert mock_ws in manager.active_connections
        assert mock_ws in manager.connection_info
        assert mock_ws.send_json.call_count >= 1
        call_args = mock_ws.send_json.call_args_list[0][0][0]
        assert call_args.get("type") == "welcome"

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self, manager, mock_ws):
        await manager.connect(mock_ws)
        assert len(manager.active_connections) == 1
        manager.disconnect(mock_ws)
        assert mock_ws not in manager.active_connections
        assert mock_ws not in manager.connection_info

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections_does_nothing(self, manager):
        await manager.broadcast({"type": "test", "data": {}})
        # No exception, no-op

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_connected(self, manager, mock_ws):
        await manager.connect(mock_ws)
        mock_ws2 = MagicMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()
        mock_ws2.client = ("127.0.0.1", 12346)
        mock_ws2.client_state = MagicMock()
        mock_ws2.client_state.value = 1
        await manager.connect(mock_ws2)
        await manager.broadcast({"type": "test", "data": {"x": 1}})
        assert mock_ws.send_json.called
        assert mock_ws2.send_json.called
        call_arg = mock_ws.send_json.call_args[0][0]
        assert call_arg["type"] == "test"
        assert call_arg["data"] == {"x": 1}
        assert "timestamp" in call_arg

    def test_get_connection_count(self, manager, mock_ws):
        assert manager.get_connection_count() == 0
        manager.active_connections.append(mock_ws)
        assert manager.get_connection_count() == 1

    @pytest.mark.asyncio
    async def test_broadcast_log(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.broadcast_log({"id": "1", "message": "hello"})
        call_arg = mock_ws.send_json.call_args_list[-1][0][0]
        assert call_arg["type"] == "log"
        assert call_arg["data"] == {"id": "1", "message": "hello"}

    @pytest.mark.asyncio
    async def test_broadcast_operation_update(self, manager, mock_ws):
        await manager.connect(mock_ws)
        await manager.broadcast_operation_update({"operation_id": "op1", "status": "completed"})
        call_arg = mock_ws.send_json.call_args_list[-1][0][0]
        assert call_arg["type"] == "operation_update"
        assert call_arg["data"]["operation_id"] == "op1"
