"""Tests for enhanced rate limit 429 response messages."""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.api.rate_limit import RateLimitConfig, RateLimitMiddleware


def _create_test_app(config: RateLimitConfig) -> FastAPI:
    """Create a minimal FastAPI app with rate limiting for testing."""
    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware, config=config)

    @test_app.post("/score")
    async def score_endpoint():
        return {"result": "ok"}

    return test_app


class TestFriendlyRateLimitResponse:
    """Tests that 429 responses include helpful information."""

    @pytest.mark.asyncio
    async def test_429_response_contains_suggestion(self):
        """Rate limit response should include Chinese suggestion message."""
        config = RateLimitConfig(
            score_endpoint_rpm=1,
            burst_allowance=0,
            anonymous_rpm=1,
            global_rpm=100,
        )
        test_app = _create_test_app(config)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First request should succeed
            resp1 = await client.post("/score", json={"text": "test"})
            assert resp1.status_code == 200

            # Second request should be rate limited
            resp2 = await client.post("/score", json={"text": "test"})
            assert resp2.status_code == 429

            data = resp2.json()
            assert "suggestion" in data
            assert "秒后重置" in data["suggestion"]
            assert "需要更多" in data["suggestion"]

    @pytest.mark.asyncio
    async def test_429_response_contains_used_and_limit(self):
        """Rate limit response should include used/limit counts."""
        config = RateLimitConfig(
            score_endpoint_rpm=1,
            burst_allowance=0,
            anonymous_rpm=1,
            global_rpm=100,
        )
        test_app = _create_test_app(config)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/score", json={"text": "test"})
            resp = await client.post("/score", json={"text": "test"})

            assert resp.status_code == 429
            data = resp.json()
            assert "used" in data
            assert "limit" in data
            assert data["used"] == data["limit"]
            assert "reset_in_seconds" in data

    @pytest.mark.asyncio
    async def test_429_response_contains_upgrade_url(self):
        """Rate limit response should include upgrade URL."""
        config = RateLimitConfig(
            score_endpoint_rpm=1,
            burst_allowance=0,
            anonymous_rpm=1,
            global_rpm=100,
        )
        test_app = _create_test_app(config)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/score", json={"text": "test"})
            resp = await client.post("/score", json={"text": "test"})

            assert resp.status_code == 429
            data = resp.json()
            assert "upgrade_url" in data
            assert data["upgrade_url"] == "/docs/pricing"

    @pytest.mark.asyncio
    async def test_429_global_limit_contains_friendly_fields(self):
        """Global rate limit 429 should also include friendly fields."""
        config = RateLimitConfig(
            score_endpoint_rpm=100,
            burst_allowance=0,
            anonymous_rpm=100,
            global_rpm=1,
        )
        test_app = _create_test_app(config)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/score", json={"text": "test"})
            resp = await client.post("/score", json={"text": "test"})

            assert resp.status_code == 429
            data = resp.json()
            assert "used" in data
            assert "limit" in data
            assert "suggestion" in data
            assert "upgrade_url" in data
