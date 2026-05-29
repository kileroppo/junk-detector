"""Tests for src/api/websocket.py and src/api/notifications.py."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.websocket import ConnectionManager
from src.api.notifications import NotificationDispatcher


class TestConnectionManager:
    """Tests for WebSocket ConnectionManager."""

    def test_initial_state(self):
        """New manager has zero connections."""
        mgr = ConnectionManager()
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_connect(self):
        """connect() adds websocket to active list."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        assert mgr.active_count == 1
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """disconnect() removes websocket from active list."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_ws(self):
        """disconnect() with unknown websocket does not raise."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        mgr.disconnect(ws)  # Should not raise
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_broadcast(self):
        """broadcast() sends JSON message to all connected clients."""
        mgr = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.broadcast("test_event", {"key": "value"})

        assert ws1.send_text.called
        assert ws2.send_text.called

        # Verify message format
        sent = ws1.send_text.call_args[0][0]
        msg = json.loads(sent)
        assert msg["event"] == "test_event"
        assert msg["data"] == {"key": "value"}
        assert "timestamp" in msg

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        """broadcast() with no connections does nothing (no error)."""
        mgr = ConnectionManager()
        await mgr.broadcast("test", {})  # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        """broadcast() removes connections that fail to send."""
        mgr = ConnectionManager()
        ws_good = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = Exception("Connection closed")

        await mgr.connect(ws_good)
        await mgr.connect(ws_dead)
        assert mgr.active_count == 2

        await mgr.broadcast("test", {"data": 1})
        assert mgr.active_count == 1  # Dead connection removed


class TestNotificationDispatcher:
    """Tests for NotificationDispatcher."""

    @pytest.mark.asyncio
    async def test_notify_score_completed_ws(self):
        """notify_score_completed broadcasts via WebSocket."""
        dispatcher = NotificationDispatcher({"websocket": True, "email": {"enabled": False}})

        with patch("src.api.websocket.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            await dispatcher.notify_score_completed({"score": 75, "summary": "Good"})
            mock_manager.broadcast.assert_called_once_with(
                "score_completed", {"score": 75, "summary": "Good"}
            )

    @pytest.mark.asyncio
    async def test_notify_monitor_alert_ws(self):
        """notify_monitor_alert broadcasts via WebSocket."""
        dispatcher = NotificationDispatcher({"websocket": True, "email": {"enabled": False}})

        with patch("src.api.websocket.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            await dispatcher.notify_monitor_alert({"title": "Bad Article"}, 25.0)
            mock_manager.broadcast.assert_called_once()
            call_args = mock_manager.broadcast.call_args
            assert call_args[0][0] == "monitor_alert"
            assert call_args[0][1]["score"] == 25.0

    @pytest.mark.asyncio
    async def test_email_disabled_no_send(self):
        """When email is disabled, no email is sent."""
        dispatcher = NotificationDispatcher({"websocket": False, "email": {"enabled": False}})

        with patch("smtplib.SMTP") as mock_smtp:
            await dispatcher.notify_score_completed({"score": 50})
            mock_smtp.assert_not_called()

    @pytest.mark.asyncio
    async def test_ws_disabled_no_broadcast(self):
        """When WebSocket is disabled, no broadcast occurs."""
        dispatcher = NotificationDispatcher({"websocket": False, "email": {"enabled": False}})

        with patch("src.api.websocket.manager") as mock_manager:
            mock_manager.broadcast = AsyncMock()
            await dispatcher.notify_score_completed({"score": 50})
            mock_manager.broadcast.assert_not_called()
