"""Tests for the /health endpoint including deep health check with caching."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def health_client(set_api_key):
    """TestClient for the FastAPI app with API key set."""
    from src.api.app import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_health_cache():
    """Reset the health cache before each test."""
    from src.api import app as app_module

    app_module._health_cache["result"] = None
    app_module._health_cache["timestamp"] = 0.0
    yield
    app_module._health_cache["result"] = None
    app_module._health_cache["timestamp"] = 0.0


class TestShallowHealth:
    """Tests for shallow health check (deep=False)."""

    def test_shallow_health_returns_ok(self, health_client):
        """GET /health returns {status: ok}."""
        response = health_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}

    def test_shallow_health_no_deep_param(self, health_client):
        """GET /health without params returns ok."""
        response = health_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestDeepHealth:
    """Tests for deep health check (deep=True)."""

    def test_deep_health_success(self, health_client):
        """GET /health?deep=true returns structured healthy response."""
        mock_response = AsyncMock()

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response):
            with patch("src.core.config.get_model_config", return_value={"primary": "test-model/test"}):
                response = health_client.get("/health?deep=true")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["llm_reachable"] is True
        assert data["model"] == "test-model/test"
        assert "latency_ms" in data
        assert isinstance(data["latency_ms"], int)

    def test_deep_health_failure_returns_503(self, health_client):
        """GET /health?deep=true returns 503 when LLM unreachable."""
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("Connection refused")):
            with patch("src.core.config.get_model_config", return_value={"primary": "test-model/test"}):
                response = health_client.get("/health?deep=true")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["llm_reachable"] is False
        assert "error" in data
        assert "Connection refused" in data["error"]

    def test_deep_health_cache_hit(self, health_client):
        """Second call within 60s returns cached result without calling LLM."""
        mock_response = AsyncMock()

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_llm:
            with patch("src.core.config.get_model_config", return_value={"primary": "test-model/test"}):
                # First call
                response1 = health_client.get("/health?deep=true")
                assert response1.status_code == 200

                # Second call should use cache
                response2 = health_client.get("/health?deep=true")
                assert response2.status_code == 200

        # LLM should only be called once
        assert mock_llm.call_count == 1

        # Both responses should be identical
        assert response1.json() == response2.json()

    def test_deep_health_cache_degraded_returns_503(self, health_client):
        """Cached degraded result returns 503."""
        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=Exception("timeout")):
            with patch("src.core.config.get_model_config", return_value={"primary": "test-model/test"}):
                # First call fails
                response1 = health_client.get("/health?deep=true")
                assert response1.status_code == 503

                # Second call returns cached 503
                response2 = health_client.get("/health?deep=true")
                assert response2.status_code == 503

    def test_deep_health_cache_expires(self, health_client):
        """Cache expires after TTL, making fresh LLM call."""
        import time

        from src.api import app as app_module

        mock_response = AsyncMock()

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_llm:
            with patch("src.core.config.get_model_config", return_value={"primary": "test-model/test"}):
                # First call
                response1 = health_client.get("/health?deep=true")
                assert response1.status_code == 200

                # Simulate cache expiration by setting timestamp in the past
                app_module._health_cache["timestamp"] = time.time() - 61.0

                # Second call should make fresh LLM call
                response2 = health_client.get("/health?deep=true")
                assert response2.status_code == 200

        # LLM should be called twice
        assert mock_llm.call_count == 2

    def test_deep_health_error_truncated(self, health_client):
        """Long error messages are truncated to 200 chars."""
        long_error = "x" * 500

        with patch("litellm.acompletion", new_callable=AsyncMock, side_effect=Exception(long_error)):
            with patch("src.core.config.get_model_config", return_value={"primary": "test-model/test"}):
                response = health_client.get("/health?deep=true")

        assert response.status_code == 503
        data = response.json()
        assert len(data["error"]) <= 200
