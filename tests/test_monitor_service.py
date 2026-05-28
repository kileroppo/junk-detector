"""Tests for src/core/monitor_service.py — MonitorService state management."""

from __future__ import annotations

import pytest

from src.core.monitor_service import MonitorService


@pytest.fixture(autouse=True)
def reset_monitor_service():
    """Reset singleton before and after each test."""
    MonitorService.reset()
    yield
    MonitorService.reset()


class TestMonitorServiceStartStop:
    """Tests for MonitorService start/stop state transitions."""

    def test_initial_state_is_stopped(self):
        """MonitorService starts in stopped state."""
        service = MonitorService()
        assert service.is_running is False

    def test_start_sets_running(self):
        """start() sets is_running to True."""
        service = MonitorService()
        service.start()
        assert service.is_running is True

    def test_stop_sets_stopped(self):
        """stop() sets is_running to False."""
        service = MonitorService()
        service.start()
        service.stop()
        assert service.is_running is False

    def test_start_idempotent(self):
        """Calling start() when already running does not raise."""
        service = MonitorService()
        service.start()
        service.start()
        assert service.is_running is True

    def test_stop_idempotent(self):
        """Calling stop() when already stopped does not raise."""
        service = MonitorService()
        service.stop()
        assert service.is_running is False

    def test_stop_when_never_started(self):
        """stop() on fresh service does not raise."""
        service = MonitorService()
        service.stop()
        assert service.is_running is False


class TestMonitorServiceSingleton:
    """Tests for MonitorService singleton behavior."""

    def test_singleton_returns_same_instance(self):
        """MonitorService() always returns the same instance."""
        service1 = MonitorService()
        service2 = MonitorService()
        assert service1 is service2

    def test_singleton_shares_state(self):
        """State changes are visible across all references."""
        service1 = MonitorService()
        service2 = MonitorService()
        service1.start()
        assert service2.is_running is True

    def test_reset_creates_new_instance(self):
        """reset() allows a fresh instance to be created."""
        service1 = MonitorService()
        service1.start()
        MonitorService.reset()
        service2 = MonitorService()
        assert service2.is_running is False


class TestMonitorServiceStats:
    """Tests for MonitorService.get_stats() method."""

    def test_get_stats_initial(self):
        """get_stats() returns zeroed stats when not started."""
        service = MonitorService()
        stats = service.get_stats()

        assert "thunder" in stats
        assert "dispatcher" in stats

    def test_get_stats_has_expected_thunder_keys(self):
        """Thunder stats contain expected keys."""
        service = MonitorService()
        stats = service.get_stats()

        thunder = stats["thunder"]
        assert "sources_count" in thunder
        assert "items_discovered" in thunder
        assert "seen_urls_count" in thunder

    def test_get_stats_has_expected_dispatcher_keys(self):
        """Dispatcher stats contain expected keys."""
        service = MonitorService()
        stats = service.get_stats()

        dispatcher = stats["dispatcher"]
        assert "in_flight" in dispatcher
        assert "max_in_flight" in dispatcher
        assert "queue_size" in dispatcher
        assert "total_scored" in dispatcher
        assert "total_failed" in dispatcher
        assert "total_retried" in dispatcher

    def test_get_stats_after_start_has_nonzero_sources(self):
        """After start(), sources_count should be non-zero."""
        service = MonitorService()
        service.start()
        stats = service.get_stats()

        assert stats["thunder"]["sources_count"] > 0

    def test_get_stats_after_stop_retains_values(self):
        """After stop(), stats retain their last values (not reset to zero)."""
        service = MonitorService()
        service.start()
        stats_running = service.get_stats()
        service.stop()
        stats_stopped = service.get_stats()

        assert stats_stopped["thunder"]["sources_count"] == stats_running["thunder"]["sources_count"]

    def test_get_stats_returns_copies(self):
        """get_stats() returns dict copies, not references to internal state."""
        service = MonitorService()
        service.start()
        stats = service.get_stats()
        stats["thunder"]["sources_count"] = 999

        fresh_stats = service.get_stats()
        assert fresh_stats["thunder"]["sources_count"] != 999
