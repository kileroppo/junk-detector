"""Tests for the notification dispatcher webhook support."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.api.notifications import NotificationDispatcher


@pytest.fixture
def dispatcher_with_webhook():
    """Create a dispatcher with webhook config."""
    config = {
        "webhook": {
            "url": "https://example.com/hook",
            "secret": "test-secret",
        }
    }
    return NotificationDispatcher(config)


@pytest.fixture
def dispatcher_no_webhook():
    """Create a dispatcher without webhook config."""
    return NotificationDispatcher({})


class TestWebhookNotification:
    """Tests for webhook POST with HMAC signature."""

    @pytest.mark.asyncio
    async def test_send_webhook_returns_false_when_no_url(self, dispatcher_no_webhook):
        """send_webhook returns False when no webhook URL is configured."""
        result = await dispatcher_no_webhook.send_webhook({"score": 30})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_posts_with_signature(self, dispatcher_with_webhook):
        """send_webhook POSTs payload with HMAC signature header."""
        payload = {"overall_score": 25, "summary": "High risk content"}

        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await dispatcher_with_webhook.send_webhook(payload)

        assert result is True
        mock_post.assert_called_once()

        # Verify signature header
        call_kwargs = mock_post.call_args[1]
        body = call_kwargs["content"]
        expected_sig = hmac.new(
            b"test-secret", body.encode(), hashlib.sha256
        ).hexdigest()
        assert call_kwargs["headers"]["X-Jianzhen-Signature"] == expected_sig
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_send_webhook_returns_false_on_error(self, dispatcher_with_webhook):
        """send_webhook returns False when HTTP request fails."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection refused")
            result = await dispatcher_with_webhook.send_webhook({"score": 10})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_webhook_returns_false_on_4xx(self, dispatcher_with_webhook):
        """send_webhook returns False when server returns 4xx."""
        mock_response = AsyncMock()
        mock_response.status_code = 403

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await dispatcher_with_webhook.send_webhook({"score": 10})

        assert result is False

    def test_config_property(self, dispatcher_with_webhook):
        """config property returns the notification config."""
        config = dispatcher_with_webhook.config
        assert "webhook" in config
        assert config["webhook"]["url"] == "https://example.com/hook"
