"""Monitor service — manages Thunder monitor running state, RSS feed fetching, and stats."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class MonitorService:
    """Singleton service that tracks monitor running state, fetches RSS feeds, and scores items.

    Thread-safety note: This singleton is designed for single-worker uvicorn deployment.
    All coroutines (fetch_feeds, get_stats, request handlers) run on the same asyncio
    event loop, so concurrent mutation of _recent_items, _seen_urls, and stat dicts is
    safe without locks. If deploying with multiple workers or threads, add explicit
    synchronization around shared mutable state.
    """

    _instance: MonitorService | None = None
    _lock = threading.Lock()
    _SEEN_URLS_MAX = 5000

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
        self._feeds: list[dict[str, str]] = []
        self._seen_urls: OrderedDict[str, None] = OrderedDict()
        self._recent_items: list[dict[str, Any]] = []
        self._task: asyncio.Task | None = None
        self._fetch_interval: int = 300
        self._auto_score: bool = True
        self._last_fetch_time: str | None = None
        self._full_score_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent full scores
        self._thunder: dict = {
            "sources_count": 0,
            "items_discovered": 0,
            "seen_urls_count": 0,
        }
        self._dispatcher: dict = {
            "in_flight": 0,
            "max_in_flight": 5,
            "queue_size": 0,
            "total_scored": 0,
            "total_failed": 0,
            "total_retried": 0,
        }

    def _load_config(self) -> None:
        """Load monitor configuration from config.yaml."""
        try:
            from src.core.config import _load_yaml

            yaml_config = _load_yaml()
            monitor_cfg = yaml_config.get("monitor", {})
            self._feeds = monitor_cfg.get("feeds", [])
            self._fetch_interval = monitor_cfg.get("fetch_interval_seconds", 300)
            self._auto_score = monitor_cfg.get("auto_score", True)
        except Exception as e:
            logger.warning("Failed to load monitor config: %s", e)
            self._feeds = []
            self._fetch_interval = 300
            self._auto_score = True

    def start(self) -> None:
        """Start the monitor. Sets state to running and starts background fetch loop."""
        self._running = True
        self._load_config()
        self._thunder = {
            "sources_count": len(self._feeds) if self._feeds else 3,
            "items_discovered": 0,
            "seen_urls_count": 0,
        }
        self._dispatcher = {
            "in_flight": 0,
            "max_in_flight": 5,
            "queue_size": 0,
            "total_scored": 0,
            "total_failed": 0,
            "total_retried": 0,
        }
        # Try to start background task if there's a running event loop
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            # No running event loop (e.g. called from sync context in tests)
            self._task = None

    def stop(self) -> None:
        """Stop the monitor. Cancel background task. Stats remain at their last values."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    @property
    def is_running(self) -> bool:
        """Return whether the monitor is currently running."""
        return self._running

    async def _run_loop(self) -> None:
        """Background loop that periodically fetches feeds."""
        try:
            while self._running:
                await self.fetch_feeds()
                await asyncio.sleep(self._fetch_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Monitor loop error: %s", e)

    async def fetch_feeds(self) -> None:
        """Fetch all configured RSS feeds and score new entries."""
        import feedparser
        import httpx

        if not self._feeds:
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            for feed_config in self._feeds:
                feed_url = feed_config.get("url", "")
                feed_name = feed_config.get("name", feed_url)
                if not feed_url:
                    continue

                try:
                    response = await client.get(feed_url)
                    response.raise_for_status()
                    parsed = feedparser.parse(response.text)

                    for entry in parsed.entries:
                        link = entry.get("link", "")
                        title = entry.get("title", "")

                        if not link or link in self._seen_urls:
                            continue

                        self._seen_urls[link] = None
                        # Evict oldest entries when over cap
                        while len(self._seen_urls) > self._SEEN_URLS_MAX:
                            self._seen_urls.popitem(last=False)  # Remove oldest
                        self._thunder["items_discovered"] += 1
                        self._thunder["seen_urls_count"] = len(self._seen_urls)

                        # Auto-score using rules-only (fast)
                        item_data: dict[str, Any] = {
                            "title": title,
                            "link": link,
                            "source": feed_name,
                            "fetched_at": datetime.now(timezone.utc).isoformat()[:19],
                            "score": None,
                            "quick_score": None,
                            "full_score": None,
                            "status": "quick_scored",
                        }

                        if self._auto_score and title:
                            try:
                                quick = self._score_item(title)
                                item_data["score"] = quick
                                item_data["quick_score"] = quick
                            except Exception as e:
                                logger.debug("Failed to quick-score item: %s", e)

                        self._recent_items.insert(0, item_data)
                        # Keep only last 20 items
                        self._recent_items = self._recent_items[:20]

                        # Spawn background full-score task
                        if self._auto_score and link:
                            try:
                                loop = asyncio.get_running_loop()
                                loop.create_task(self._full_score_item(item_data))
                            except RuntimeError:
                                pass  # No event loop (sync context)

                except Exception as e:
                    logger.debug("Failed to fetch feed %s: %s", feed_name, e)

        self._last_fetch_time = datetime.now(timezone.utc).isoformat()[:19]
        self._thunder["sources_count"] = len(self._feeds)

    def _score_item(self, text: str) -> float:
        """Score an item using rules-only (fast path, no LLM)."""
        from src.core.config import load_config
        from src.core.rules import apply_rules
        from src.core.scorer import _calculate_overall
        from src.models.score import DimensionScores

        rule_result = apply_rules(text)

        # Build dimensions from rules, defaulting to 50 for positive, 0 for negative
        dims_dict: dict[str, float] = {}
        for dim in ["originality", "info_density", "reasoning_quality", "readability", "timeliness"]:
            dims_dict[dim] = rule_result.dimension_overrides.get(dim, 50.0)
        for dim in ["ai_generated_prob", "emotional_manipulation", "advertorial_prob", "scam_prob"]:
            dims_dict[dim] = rule_result.dimension_overrides.get(dim, 0.0)

        dimensions = DimensionScores(**dims_dict)
        config = load_config()
        overall = _calculate_overall(dimensions, config)
        return overall

    async def _full_score_item(self, item_data: dict) -> None:
        """Background task: extract URL content and run full scoring.

        Updates item in _recent_items from 'quick_scored' to 'fully_scored'.
        Bounded by _full_score_semaphore to limit concurrency.
        """
        async with self._full_score_semaphore:
            link = item_data.get("link", "")
            if not link:
                return

            try:
                item_data["status"] = "scoring_full"

                from src.extractors.web import extract_from_url

                content = await extract_from_url(link)

                from src.core.scorer import score

                result = await score(content.text)

                item_data["full_score"] = result.overall_score
                item_data["score"] = result.overall_score
                item_data["status"] = "fully_scored"
                self._dispatcher["total_scored"] += 1

            except Exception as e:
                logger.debug("Full scoring failed for %s: %s", link, e)
                # Keep quick_scored status, don't update score
                item_data["status"] = "quick_scored"
                self._dispatcher["total_failed"] += 1

    def add_feed(self, name: str, url: str) -> None:
        """Add a new feed to the internal feeds list.

        Args:
            name: Display name for the feed.
            url: RSS feed URL.

        Raises:
            ValueError: If the URL does not start with http:// or https://.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError("Feed URL must start with http:// or https://")
        self._feeds.append({"name": name, "url": url})
        self._thunder["sources_count"] = len(self._feeds)

    def remove_feed(self, index: int) -> bool:
        """Remove a feed by index from the internal feeds list.

        Args:
            index: Zero-based index of the feed to remove.

        Returns:
            True if the feed was removed, False if index was invalid.
        """
        if 0 <= index < len(self._feeds):
            self._feeds.pop(index)
            self._thunder["sources_count"] = len(self._feeds)
            return True
        return False

    def get_stats(self) -> dict:
        """Return current stats for thunder and dispatcher, plus recent items."""
        return {
            "thunder": dict(self._thunder),
            "dispatcher": dict(self._dispatcher),
            "recent_items": list(self._recent_items[:10]),
            "feeds": list(self._feeds),
            "last_fetch_time": self._last_fetch_time,
        }

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (useful for testing)."""
        if cls._instance is not None:
            # Cancel any running task
            if cls._instance._task is not None:
                cls._instance._task.cancel()
                cls._instance._task = None
        cls._instance = None
