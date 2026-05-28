"""Tests for monitor start/stop API routes in src/web/router.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.core.monitor_service import MonitorService


@pytest.fixture(autouse=True)
def reset_monitor_service():
    """Reset singleton before and after each test."""
    MonitorService.reset()
    yield
    MonitorService.reset()


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes with rate limiting bypassed."""
    from src.api.app import app

    with patch("src.api.rate_limit.SlidingWindowLimiter.is_allowed", return_value=True):
        with TestClient(app) as c:
            yield c


class TestMonitorStartEndpoint:
    """Tests for POST /api/monitor/start."""

    def test_start_returns_200(self, web_client):
        """POST /api/monitor/start returns 200."""
        response = web_client.post("/api/monitor/start")
        assert response.status_code == 200

    def test_start_sets_running_state(self, web_client):
        """POST /api/monitor/start sets monitor to running."""
        web_client.post("/api/monitor/start")
        service = MonitorService()
        assert service.is_running is True

    def test_start_returns_hx_trigger(self, web_client):
        """POST /api/monitor/start returns HX-Trigger header."""
        response = web_client.post("/api/monitor/start")
        assert "HX-Trigger" in response.headers
        assert "showToast" in response.headers["HX-Trigger"]

    def test_start_when_already_running(self, web_client):
        """POST /api/monitor/start when already running still returns 200."""
        web_client.post("/api/monitor/start")
        response = web_client.post("/api/monitor/start")
        assert response.status_code == 200


class TestMonitorStopEndpoint:
    """Tests for POST /api/monitor/stop."""

    def test_stop_returns_200(self, web_client):
        """POST /api/monitor/stop returns 200."""
        response = web_client.post("/api/monitor/stop")
        assert response.status_code == 200

    def test_stop_sets_stopped_state(self, web_client):
        """POST /api/monitor/stop sets monitor to stopped."""
        web_client.post("/api/monitor/start")
        web_client.post("/api/monitor/stop")
        service = MonitorService()
        assert service.is_running is False

    def test_stop_returns_hx_trigger(self, web_client):
        """POST /api/monitor/stop returns HX-Trigger header."""
        response = web_client.post("/api/monitor/stop")
        assert "HX-Trigger" in response.headers
        assert "showToast" in response.headers["HX-Trigger"]

    def test_stop_when_already_stopped(self, web_client):
        """POST /api/monitor/stop when already stopped still returns 200."""
        response = web_client.post("/api/monitor/stop")
        assert response.status_code == 200


class TestMonitorStatsAfterStartStop:
    """Tests for /partials/monitor-stats reflecting start/stop state."""

    def test_stats_shows_running_after_start(self, web_client):
        """After start, /partials/monitor-stats shows running state."""
        web_client.post("/api/monitor/start")
        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200
        assert "监控运行中" in response.text

    def test_stats_shows_stopped_after_stop(self, web_client):
        """After stop, /partials/monitor-stats shows stopped state."""
        web_client.post("/api/monitor/start")
        web_client.post("/api/monitor/stop")
        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200
        assert "监控已停止" in response.text

    def test_stats_shows_stopped_initially(self, web_client):
        """Without start, /partials/monitor-stats shows stopped state."""
        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200
        assert "监控已停止" in response.text

    def test_stats_shows_nonzero_sources_after_start(self, web_client):
        """After start, stats show non-zero sources_count."""
        web_client.post("/api/monitor/start")
        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200
        # sources_count should be non-zero (from configured feeds)
        assert ">2<" in response.text or ">3<" in response.text


class TestMonitorHXTriggerFormat:
    """Tests verifying HX-Trigger header contains both showToast and refreshMonitorStats."""

    def test_start_hx_trigger_contains_refresh(self, web_client):
        """POST /api/monitor/start HX-Trigger header contains refreshMonitorStats."""
        response = web_client.post("/api/monitor/start")
        assert "HX-Trigger" in response.headers
        assert "refreshMonitorStats" in response.headers["HX-Trigger"]

    def test_stop_hx_trigger_contains_refresh(self, web_client):
        """POST /api/monitor/stop HX-Trigger header contains refreshMonitorStats."""
        response = web_client.post("/api/monitor/stop")
        assert "HX-Trigger" in response.headers
        assert "refreshMonitorStats" in response.headers["HX-Trigger"]

    def test_start_hx_trigger_is_valid_json_with_both_keys(self, web_client):
        """POST /api/monitor/start HX-Trigger is parseable JSON with both keys."""
        import json

        response = web_client.post("/api/monitor/start")
        trigger = response.headers["HX-Trigger"]
        data = json.loads(trigger)
        assert "showToast" in data
        assert "refreshMonitorStats" in data
        assert data["showToast"]["message"] == "Monitor started"
        assert data["showToast"]["type"] == "success"

    def test_stop_hx_trigger_is_valid_json_with_both_keys(self, web_client):
        """POST /api/monitor/stop HX-Trigger is parseable JSON with both keys."""
        import json

        response = web_client.post("/api/monitor/stop")
        trigger = response.headers["HX-Trigger"]
        data = json.loads(trigger)
        assert "showToast" in data
        assert "refreshMonitorStats" in data
        assert data["showToast"]["message"] == "Monitor stopped"
        assert data["showToast"]["type"] == "info"
