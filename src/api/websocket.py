"""WebSocket support for real-time notifications.

Dao De Jing: bu zhao er zi lai - information comes to you
proactively without repeated querying.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.auth.service import AuthService

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, int | None] = {}

    @property
    def active_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket, user_id: int | None = None) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections[websocket] = user_id
        logger.info("WebSocket connected. Active: %d", self.active_count)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self._connections:
            del self._connections[websocket]
        logger.info("WebSocket disconnected. Active: %d", self.active_count)

    async def broadcast(self, event: str, data: dict) -> None:
        """Broadcast a message to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({
            "event": event,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False)

        disconnected: list[WebSocket] = []
        for connection in self._connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


# Global connection manager instance
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for receiving real-time notifications."""
    token = websocket.query_params.get("token")
    user_id: int | None = None

    if token:
        try:
            payload = AuthService.verify_token(token)
            user_id = payload["user_id"]
        except ValueError:
            await websocket.close(code=4001, reason="Invalid token")
            return

    await manager.connect(websocket, user_id=user_id)
    try:
        while True:
            # Keep connection alive, handle incoming messages (ping/pong)
            data = await websocket.receive_text()
            # Echo back as acknowledgment
            if data == "ping":
                await websocket.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
