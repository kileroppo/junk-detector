"""Tests for SSE streaming endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import app


class TestStreamingEndpoint:
    """Tests for the /score/stream endpoint."""

    @pytest.mark.asyncio
    async def test_stream_endpoint_exists(self):
        """POST /score/stream should be a valid route."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/score/stream",
                json={"text": "test content"},
                headers={"Accept": "text/event-stream"},
            )
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_stream_returns_event_stream_content_type(self):
        """Streaming response should have text/event-stream content type."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/score/stream",
                json={"text": "test content for streaming"},
                headers={"Accept": "text/event-stream"},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_fallback_without_accept_header(self):
        """Without text/event-stream Accept header, should fall back to normal scoring."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/score/stream",
                json={"text": "test content"},
                headers={"Accept": "application/json"},
            )
            # Should not be 404 - the endpoint exists
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_stream_response_contains_events(self):
        """Streaming response body should contain SSE event markers."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/score/stream",
                json={"text": "test content for events"},
                headers={"Accept": "text/event-stream"},
            )
            body = response.text
            # Should have at least one SSE event
            assert "event:" in body
