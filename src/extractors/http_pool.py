"""Shared httpx.AsyncClient with connection pooling for source fetchers."""
from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Get or create the shared httpx.AsyncClient with connection pool limits."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
            timeout=10.0,
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    """Close the shared client. Call on app shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None
