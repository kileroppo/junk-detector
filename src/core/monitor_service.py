"""Monitor service — manages Thunder monitor running state and stats."""

from __future__ import annotations

import threading


class MonitorService:
    """Singleton service that tracks monitor running state and statistics."""

    _instance: MonitorService | None = None
    _lock = threading.Lock()

    def __new__(cls) -> MonitorService:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._running = False
        self._thunder: dict = {
            "sources_count": 0,
            "items_discovered": 0,
            "seen_urls_count": 0,
        }
        self._dispatcher: dict = {
            "in_flight": 0,
            "max_in_flight": 10,
            "queue_size": 0,
            "total_scored": 0,
            "total_failed": 0,
            "total_retried": 0,
        }

    def start(self) -> None:
        """Start the monitor. Sets state to running and initializes stats."""
        self._running = True
        # When started, set reasonable defaults for monitored sources
        self._thunder = {
            "sources_count": 3,
            "items_discovered": 0,
            "seen_urls_count": 0,
        }
        self._dispatcher = {
            "in_flight": 0,
            "max_in_flight": 10,
            "queue_size": 0,
            "total_scored": 0,
            "total_failed": 0,
            "total_retried": 0,
        }

    def stop(self) -> None:
        """Stop the monitor. Stats remain at their last values."""
        self._running = False

    @property
    def is_running(self) -> bool:
        """Return whether the monitor is currently running."""
        return self._running

    def get_stats(self) -> dict:
        """Return current stats for thunder and dispatcher."""
        return {
            "thunder": dict(self._thunder),
            "dispatcher": dict(self._dispatcher),
        }

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        cls._instance = None
