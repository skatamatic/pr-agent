import asyncio
import json
import logging
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class WebSocketManager:
    """
    Manages WebSocket connections for real-time dashboard updates
    """
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_info[websocket] = {
            "connected_at": asyncio.get_event_loop().time(),
            "client_info": websocket.client
        }
        logger.info(f"WebSocket connected: {websocket.client}")
        
        # Send welcome message
        await self.send_personal_message({
            "type": "welcome",
            "message": "Connected to PR Agent Dashboard",
            "timestamp": asyncio.get_event_loop().time()
        }, websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            if websocket in self.connection_info:
                del self.connection_info[websocket]
            logger.info(f"WebSocket disconnected: {websocket.client}")
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send a message to a specific WebSocket connection"""
        try:
            # Check if websocket is still connected before sending
            if websocket.client_state.value == 1:  # CONNECTED state
                await websocket.send_json(message)
            else:
                logger.debug(f"Skipping message to disconnected WebSocket: {websocket.client}")
                self.disconnect(websocket)
        except Exception as e:
            logger.debug(f"Error sending personal message to {websocket.client}: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients"""
        if not self.active_connections:
            return
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = asyncio.get_event_loop().time()
        
        disconnected = []
        
        for connection in self.active_connections:
            try:
                # Check if connection is still active before sending
                if connection.client_state.value == 1:  # CONNECTED state
                    await connection.send_json(message)
                else:
                    logger.debug(f"Skipping broadcast to disconnected WebSocket: {connection.client}")
                    disconnected.append(connection)
            except WebSocketDisconnect:
                disconnected.append(connection)
            except Exception as e:
                logger.debug(f"Error broadcasting to {connection.client}: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
        
        if disconnected:
            logger.info(f"Removed {len(disconnected)} disconnected clients")
    
    async def broadcast_log(self, log_data: Dict[str, Any]):
        """Broadcast a new log entry"""
        await self.broadcast({
            "type": "log",
            "data": log_data
        })
    
    async def broadcast_operation_update(self, operation_data: Dict[str, Any]):
        """Broadcast an operation status update"""
        await self.broadcast({
            "type": "operation_update",
            "data": operation_data
        })
    
    async def broadcast_metrics_update(self, metrics_data: Dict[str, Any]):
        """Broadcast metrics update"""
        await self.broadcast({
            "type": "metrics_update",
            "data": metrics_data
        })
    
    async def broadcast_system_status(self, status_data: Dict[str, Any]):
        """Broadcast system status update"""
        await self.broadcast({
            "type": "system_status",
            "data": status_data
        })
    
    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len(self.active_connections)
    
    def get_connection_info(self) -> List[Dict[str, Any]]:
        """Get information about all active connections"""
        current_time = asyncio.get_event_loop().time()
        return [
            {
                "client": str(conn.client),
                "connected_at": info["connected_at"],
                "duration": current_time - info["connected_at"]
            }
            for conn, info in self.connection_info.items()
        ]
    
    async def send_ping_to_all(self):
        """Send ping to all connections to keep them alive"""
        await self.broadcast({
            "type": "ping",
            "message": "keepalive"
        })
    
    async def start_keepalive_task(self, interval: int = 30):
        """Start a background task to send periodic pings"""
        async def keepalive():
            while True:
                await asyncio.sleep(interval)
                if self.active_connections:
                    await self.send_ping_to_all()
        
        return asyncio.create_task(keepalive()) 