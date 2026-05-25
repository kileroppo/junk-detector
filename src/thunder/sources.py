"""Content sources for Thunder stream monitoring."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from src.thunder.models import FeedItem, SourceConfig

logger = logging.getLogger("thunder")


class ContentSource(ABC):
    """Abstract base class for content sources."""

    @abstractmethod
    async def poll(self) -> list[FeedItem]:
        """Poll the source for new items.

        Returns:
            List of newly discovered FeedItems.
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """Initialize the source (e.g., open connections)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Clean up the source (e.g., close connections)."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of this source."""
        ...


class RSSSource(ContentSource):
    """Polls RSS/Atom feeds using httpx + feedparser."""

    def __init__(self, config: SourceConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._last_polled_at: datetime | None = None
        self._etag: str | None = None
        self._modified: str | None = None

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def config(self) -> SourceConfig:
        return self._config

    @property
    def last_polled_at(self) -> datetime | None:
        return self._last_polled_at

    async def start(self) -> None:
        """Open the HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Thunder/1.0 (junk-detector)"},
        )
        logger.info(f"RSSSource '{self.name}' started, url={self._config.url}")

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info(f"RSSSource '{self.name}' stopped")

    async def poll(self) -> list[FeedItem]:
        """Fetch the RSS feed and return new items.

        Uses conditional requests (ETag/Last-Modified) to avoid
        re-downloading unchanged feeds.

        Returns:
            List of FeedItems parsed from the feed, or empty list on error.
        """
        if self._client is None:
            await self.start()

        try:
            headers: dict[str, str] = {}
            if self._etag:
                headers["If-None-Match"] = self._etag
            if self._modified:
                headers["If-Modified-Since"] = self._modified

            response = await self._client.get(self._config.url, headers=headers)  # type: ignore[union-attr]

            # Not modified — no new content
            if response.status_code == 304:
                self._last_polled_at = datetime.now(timezone.utc)
                return []

            response.raise_for_status()

            # Update conditional request headers for next poll
            if "etag" in response.headers:
                self._etag = response.headers["etag"]
            if "last-modified" in response.headers:
                self._modified = response.headers["last-modified"]

            # Parse the feed
            import feedparser

            feed = feedparser.parse(response.text)

            items: list[FeedItem] = []
            for entry in feed.entries:
                item = FeedItem.from_rss_entry(entry, source_name=self.name)
                item.priority = self._config.priority
                items.append(item)

            self._last_polled_at = datetime.now(timezone.utc)
            logger.debug(f"RSSSource '{self.name}' polled: {len(items)} entries found")
            return items

        except Exception as e:
            logger.warning(f"RSSSource '{self.name}' poll failed: {type(e).__name__}: {e}")
            return []


class WebhookSource(ContentSource):
    """Receives items pushed by external code (e.g., FastAPI webhook endpoint).

    Items are pushed via the `receive()` method and collected on `poll()`.
    """

    def __init__(self, config: SourceConfig) -> None:
        self._config = config
        self._queue: asyncio.Queue[FeedItem] = asyncio.Queue()

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def config(self) -> SourceConfig:
        return self._config

    async def start(self) -> None:
        """No-op for webhook source — ready immediately."""
        logger.info(f"WebhookSource '{self.name}' started")

    async def stop(self) -> None:
        """No-op for webhook source."""
        logger.info(f"WebhookSource '{self.name}' stopped")

    async def receive(self, item: FeedItem) -> None:
        """Push an item into the internal queue.

        Called by external code (e.g., a FastAPI webhook endpoint).

        Args:
            item: The FeedItem to enqueue.
        """
        await self._queue.put(item)
        logger.debug(f"WebhookSource '{self.name}' received item: {item.url}")

    async def poll(self) -> list[FeedItem]:
        """Drain the internal queue and return all pending items.

        Returns:
            List of all FeedItems currently in the queue.
        """
        items: list[FeedItem] = []
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                items.append(item)
            except asyncio.QueueEmpty:
                break

        if items:
            logger.debug(f"WebhookSource '{self.name}' polled: {len(items)} items drained")
        return items
