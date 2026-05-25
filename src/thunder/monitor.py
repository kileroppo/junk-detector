"""Thunder monitor — orchestrates polling of content sources."""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from src.thunder.models import FeedItem
from src.thunder.sources import ContentSource

logger = logging.getLogger("thunder")

# Maximum number of URLs to track for deduplication
_MAX_SEEN_URLS = 10_000


class ThunderMonitor:
    """Main Thunder monitor that polls content sources and pushes items to a queue.

    Manages multiple content sources, deduplicates discovered items,
    and feeds them into an output queue for downstream processing.

    Args:
        output_queue: The asyncio queue to push discovered FeedItems into.
        sources: Initial list of content sources to monitor.
    """

    def __init__(
        self,
        output_queue: asyncio.Queue[FeedItem],
        sources: list[ContentSource] | None = None,
    ) -> None:
        self._output_queue = output_queue
        self._sources: list[ContentSource] = sources or []
        self._seen_urls: deque[str] = deque(maxlen=_MAX_SEEN_URLS)
        self._seen_urls_set: set[str] = set()
        self._running: bool = False
        self._tasks: list[asyncio.Task] = []
        self._items_discovered: int = 0

    @property
    def stats(self) -> dict:
        """Return monitoring statistics.

        Returns:
            Dict with sources_count, items_discovered, and seen_urls_count.
        """
        return {
            "sources_count": len(self._sources),
            "items_discovered": self._items_discovered,
            "seen_urls_count": len(self._seen_urls_set),
        }

    async def start(self) -> None:
        """Start the monitor — launches a polling task for each source.

        Calls start() on each source, then creates an asyncio task
        for each source's poll loop.
        """
        if self._running:
            logger.warning("ThunderMonitor is already running")
            return

        self._running = True
        logger.info(f"ThunderMonitor starting with {len(self._sources)} source(s)")

        for source in self._sources:
            await source.start()
            task = asyncio.create_task(
                self._poll_source(source), name=f"thunder-poll-{source.name}"
            )
            self._tasks.append(task)

        logger.info("ThunderMonitor started")

    async def stop(self) -> None:
        """Stop the monitor — cancels all polling tasks and stops sources.

        Sets _running to False, cancels all tasks, and waits for them
        to finish. Then stops each source.
        """
        if not self._running:
            return

        self._running = False
        logger.info("ThunderMonitor stopping...")

        # Cancel all polling tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to finish (suppressing CancelledError)
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Stop all sources
        for source in self._sources:
            try:
                await source.stop()
            except Exception as e:
                logger.warning(f"Error stopping source '{source.name}': {e}")

        logger.info("ThunderMonitor stopped")

    async def add_source(self, source: ContentSource) -> None:
        """Dynamically add a new source at runtime.

        If the monitor is already running, the source is started immediately
        and a polling task is created for it.

        Args:
            source: The content source to add.
        """
        self._sources.append(source)
        logger.info(f"Added source '{source.name}'")

        if self._running:
            await source.start()
            task = asyncio.create_task(
                self._poll_source(source), name=f"thunder-poll-{source.name}"
            )
            self._tasks.append(task)

    async def _poll_source(self, source: ContentSource) -> None:
        """Infinite poll loop for a single source.

        Polls the source, deduplicates items, and pushes new ones
        to the output queue. Sleeps between polls.

        Catches all exceptions to prevent one bad source from
        crashing the entire monitor.

        Args:
            source: The content source to poll.
        """
        # Determine poll interval from source config if available
        poll_interval = getattr(getattr(source, "_config", None), "poll_interval_seconds", 300)

        while self._running:
            try:
                items = await source.poll()
                new_items = self._deduplicate(items)

                for item in new_items:
                    await self._output_queue.put(item)
                    self._items_discovered += 1

                if new_items:
                    logger.info(f"Source '{source.name}': discovered {len(new_items)} new item(s)")

            except asyncio.CancelledError:
                # Task was cancelled during stop() — exit cleanly
                raise
            except Exception as e:
                logger.error(f"Error polling source '{source.name}': {type(e).__name__}: {e}")

            # Sleep until next poll
            try:
                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                raise

    def _deduplicate(self, items: list[FeedItem]) -> list[FeedItem]:
        """Filter out items whose URLs have already been seen.

        Maintains a bounded deque of seen URLs. When the deque reaches
        max capacity, oldest entries are automatically evicted and
        removed from the lookup set.

        Args:
            items: List of FeedItems to check.

        Returns:
            List of FeedItems not previously seen.
        """
        new_items: list[FeedItem] = []

        for item in items:
            if item.url in self._seen_urls_set:
                continue

            # If deque is at capacity, the oldest URL will be evicted
            if len(self._seen_urls) == _MAX_SEEN_URLS:
                evicted_url = self._seen_urls[0]  # will be auto-removed by deque
                self._seen_urls_set.discard(evicted_url)

            self._seen_urls.append(item.url)
            self._seen_urls_set.add(item.url)
            new_items.append(item)

        return new_items
