"""Tests for the thunder module: models, sources, and monitor."""

from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.thunder.models import FeedItem, SourceConfig
from src.thunder.monitor import ThunderMonitor, _MAX_SEEN_URLS
from src.thunder.sources import RSSSource, WebhookSource


# ---------- FeedItem model tests ----------


class TestFeedItem:
    """Tests for the FeedItem model."""

    def test_auto_generated_id_from_url_hash(self):
        """FeedItem id is auto-generated as sha256(url)[:16] when not provided."""
        item = FeedItem(url="https://example.com/article1", source_name="test")
        expected_id = hashlib.sha256("https://example.com/article1".encode()).hexdigest()[:16]
        assert item.id == expected_id

    def test_explicit_id_not_overridden(self):
        """FeedItem keeps explicit id if provided."""
        item = FeedItem(id="custom-id", url="https://example.com/article1", source_name="test")
        assert item.id == "custom-id"

    def test_default_priority(self):
        """FeedItem default priority is 5."""
        item = FeedItem(url="https://example.com/a", source_name="test")
        assert item.priority == 5

    def test_discovered_at_auto_set(self):
        """discovered_at is auto-set to approximately now."""
        before = datetime.now(timezone.utc)
        item = FeedItem(url="https://example.com/a", source_name="test")
        after = datetime.now(timezone.utc)
        assert before <= item.discovered_at <= after

    def test_priority_validation_range(self):
        """Priority must be between 1 and 10."""
        with pytest.raises(ValidationError):
            FeedItem(url="https://example.com/a", source_name="test", priority=0)
        with pytest.raises(ValidationError):
            FeedItem(url="https://example.com/a", source_name="test", priority=11)

    def test_from_rss_entry_with_link(self):
        """from_rss_entry uses 'link' field as URL."""
        entry = {
            "link": "https://example.com/post",
            "title": "Test Post",
        }
        item = FeedItem.from_rss_entry(entry, source_name="rss-feed")
        assert item.url == "https://example.com/post"
        assert item.title == "Test Post"
        assert item.source_name == "rss-feed"

    def test_from_rss_entry_fallback_to_id(self):
        """from_rss_entry falls back to 'id' if 'link' is missing."""
        entry = {
            "id": "https://example.com/entry-id",
            "title": "Fallback Entry",
        }
        item = FeedItem.from_rss_entry(entry, source_name="feed")
        assert item.url == "https://example.com/entry-id"

    def test_from_rss_entry_no_link_no_id(self):
        """from_rss_entry uses empty string if neither link nor id present."""
        entry = {"title": "No URL Entry"}
        item = FeedItem.from_rss_entry(entry, source_name="feed")
        assert item.url == ""

    def test_from_rss_entry_no_title(self):
        """from_rss_entry handles missing title gracefully."""
        entry = {"link": "https://example.com/no-title"}
        item = FeedItem.from_rss_entry(entry, source_name="feed")
        assert item.title is None

    def test_from_rss_entry_with_published_parsed(self):
        """from_rss_entry parses published_parsed time struct."""
        # time.struct_time for 2024-01-15 12:00:00
        published = time.strptime("2024-01-15 12:00:00", "%Y-%m-%d %H:%M:%S")
        entry = {
            "link": "https://example.com/dated",
            "title": "Dated Post",
            "published_parsed": published,
        }
        item = FeedItem.from_rss_entry(entry, source_name="feed")
        assert item.discovered_at.year == 2024
        assert item.discovered_at.month == 1
        assert item.discovered_at.day == 15

    def test_from_rss_entry_with_none_published_parsed(self):
        """from_rss_entry handles None published_parsed."""
        entry = {
            "link": "https://example.com/no-date",
            "published_parsed": None,
        }
        item = FeedItem.from_rss_entry(entry, source_name="feed")
        # Should use current time, not crash
        assert item.discovered_at is not None

    def test_from_rss_entry_with_invalid_published_parsed(self):
        """from_rss_entry handles invalid published_parsed gracefully."""
        entry = {
            "link": "https://example.com/bad-date",
            "published_parsed": "not a time struct",
        }
        item = FeedItem.from_rss_entry(entry, source_name="feed")
        # Should fall back to now, not raise
        assert item.discovered_at is not None


# ---------- SourceConfig model tests ----------


class TestSourceConfig:
    """Tests for the SourceConfig model."""

    def test_defaults(self):
        """SourceConfig has sensible defaults."""
        config = SourceConfig(name="test-source", type="rss", url="https://example.com/rss")
        assert config.poll_interval_seconds == 300
        assert config.priority == 5
        assert config.enabled is True

    def test_valid_priority_range(self):
        """Priority between 1 and 10 is valid."""
        config = SourceConfig(name="t", type="rss", url="http://x.com", priority=1)
        assert config.priority == 1
        config = SourceConfig(name="t", type="rss", url="http://x.com", priority=10)
        assert config.priority == 10

    def test_invalid_priority_below_range(self):
        """Priority below 1 raises validation error."""
        with pytest.raises(ValidationError):
            SourceConfig(name="t", type="rss", url="http://x.com", priority=0)

    def test_invalid_priority_above_range(self):
        """Priority above 10 raises validation error."""
        with pytest.raises(ValidationError):
            SourceConfig(name="t", type="rss", url="http://x.com", priority=11)

    def test_poll_interval_minimum(self):
        """poll_interval_seconds must be >= 1."""
        with pytest.raises(ValidationError):
            SourceConfig(name="t", type="rss", url="http://x.com", poll_interval_seconds=0)

    def test_valid_poll_interval(self):
        """poll_interval_seconds >= 1 is valid."""
        config = SourceConfig(name="t", type="rss", url="http://x.com", poll_interval_seconds=1)
        assert config.poll_interval_seconds == 1

    def test_type_literal(self):
        """type must be 'rss' or 'webhook'."""
        with pytest.raises(ValidationError):
            SourceConfig(name="t", type="invalid", url="http://x.com")


# ---------- WebhookSource tests ----------


class TestWebhookSource:
    """Tests for the WebhookSource."""

    def _make_source(self, name: str = "webhook-test") -> WebhookSource:
        config = SourceConfig(name=name, type="webhook", url="http://localhost/hook")
        return WebhookSource(config)

    async def test_start_is_noop(self):
        """start() completes without error (no-op)."""
        source = self._make_source()
        await source.start()  # Should not raise

    async def test_stop_is_noop(self):
        """stop() completes without error (no-op)."""
        source = self._make_source()
        await source.stop()  # Should not raise

    async def test_name_property(self):
        """name property returns config name."""
        source = self._make_source("my-hook")
        assert source.name == "my-hook"

    async def test_config_property(self):
        """config property returns the SourceConfig."""
        source = self._make_source("hook")
        assert source.config.name == "hook"
        assert source.config.type == "webhook"

    async def test_receive_adds_item(self):
        """receive() adds an item that can be retrieved via poll()."""
        source = self._make_source()
        item = FeedItem(url="https://example.com/new", source_name="hook")
        await source.receive(item)
        results = await source.poll()
        assert len(results) == 1
        assert results[0].url == "https://example.com/new"

    async def test_poll_drains_queue(self):
        """poll() returns all items and empties the queue."""
        source = self._make_source()
        for i in range(3):
            await source.receive(FeedItem(url=f"https://example.com/{i}", source_name="hook"))

        results = await source.poll()
        assert len(results) == 3

        # Queue is now empty
        results2 = await source.poll()
        assert len(results2) == 0

    async def test_poll_returns_empty_when_no_items(self):
        """poll() returns empty list when no items have been received."""
        source = self._make_source()
        results = await source.poll()
        assert results == []


# ---------- RSSSource tests ----------


class TestRSSSource:
    """Tests for the RSSSource."""

    def _make_source(self, name: str = "rss-test", url: str = "https://example.com/feed.xml") -> RSSSource:
        config = SourceConfig(name=name, type="rss", url=url, poll_interval_seconds=60)
        return RSSSource(config)

    async def test_name_and_config(self):
        """name and config properties return correct values."""
        source = self._make_source("my-rss")
        assert source.name == "my-rss"
        assert source.config.url == "https://example.com/feed.xml"

    async def test_start_creates_client(self):
        """start() initializes the httpx client."""
        source = self._make_source()
        assert source._client is None
        await source.start()
        assert source._client is not None
        await source.stop()

    async def test_stop_closes_client(self):
        """stop() closes and sets client to None."""
        source = self._make_source()
        await source.start()
        assert source._client is not None
        await source.stop()
        assert source._client is None

    async def test_poll_parses_rss_feed(self):
        """poll() with mocked httpx returns parsed FeedItems."""
        source = self._make_source()

        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Test Feed</title>
            <item>
              <title>Article 1</title>
              <link>https://example.com/article1</link>
            </item>
            <item>
              <title>Article 2</title>
              <link>https://example.com/article2</link>
            </item>
          </channel>
        </rss>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = rss_xml
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        source._client = mock_client

        items = await source.poll()
        assert len(items) == 2
        assert items[0].title == "Article 1"
        assert items[0].url == "https://example.com/article1"
        assert items[1].title == "Article 2"
        assert items[0].source_name == "rss-test"

    async def test_poll_sends_conditional_headers(self):
        """poll() sends ETag and If-Modified-Since headers when available."""
        source = self._make_source()

        # Set stored conditional headers
        source._etag = '"abc123"'
        source._modified = "Mon, 01 Jan 2024 00:00:00 GMT"

        rss_xml = """<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = rss_xml
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        source._client = mock_client

        await source.poll()

        # Verify correct headers were sent
        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers["If-None-Match"] == '"abc123"'
        assert headers["If-Modified-Since"] == "Mon, 01 Jan 2024 00:00:00 GMT"

    async def test_poll_stores_etag_from_response(self):
        """poll() stores ETag and Last-Modified from response headers."""
        source = self._make_source()

        rss_xml = """<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = rss_xml
        mock_response.headers = {"etag": '"new-etag"', "last-modified": "Tue, 02 Jan 2024 00:00:00 GMT"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        source._client = mock_client

        await source.poll()

        assert source._etag == '"new-etag"'
        assert source._modified == "Tue, 02 Jan 2024 00:00:00 GMT"

    async def test_poll_304_returns_empty(self):
        """poll() returns empty list on 304 Not Modified."""
        source = self._make_source()

        mock_response = MagicMock()
        mock_response.status_code = 304

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        source._client = mock_client

        items = await source.poll()
        assert items == []
        assert source.last_polled_at is not None

    async def test_poll_network_error_returns_empty(self):
        """poll() returns empty list on network error."""
        source = self._make_source()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        source._client = mock_client

        items = await source.poll()
        assert items == []

    async def test_poll_auto_starts_client(self):
        """poll() auto-starts client if not already started."""
        source = self._make_source()
        assert source._client is None

        # Mock start to track it was called, then set a mock client
        original_start = source.start

        async def mock_start():
            # Simulate start behavior
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("test"))
            source._client = mock_client

        source.start = mock_start

        items = await source.poll()
        assert items == []  # Error caught gracefully


# ---------- ThunderMonitor tests ----------


class TestThunderMonitor:
    """Tests for the ThunderMonitor."""

    def _make_feed_item(self, url: str = "https://example.com/item") -> FeedItem:
        return FeedItem(url=url, source_name="test")

    def test_deduplicate_filters_seen_urls(self):
        """_deduplicate filters items whose URLs have already been seen."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue)

        items = [
            self._make_feed_item("https://example.com/1"),
            self._make_feed_item("https://example.com/2"),
        ]

        # First call - all items are new
        result = monitor._deduplicate(items)
        assert len(result) == 2

        # Second call with same items - all filtered
        result = monitor._deduplicate(items)
        assert len(result) == 0

    def test_deduplicate_partial_overlap(self):
        """_deduplicate only filters already-seen items."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue)

        items1 = [self._make_feed_item("https://example.com/1")]
        monitor._deduplicate(items1)

        items2 = [
            self._make_feed_item("https://example.com/1"),  # seen
            self._make_feed_item("https://example.com/2"),  # new
        ]
        result = monitor._deduplicate(items2)
        assert len(result) == 1
        assert result[0].url == "https://example.com/2"

    def test_deduplicate_evicts_oldest_at_capacity(self):
        """_deduplicate evicts oldest URLs when at _MAX_SEEN_URLS capacity."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue)

        # Fill to capacity
        items = [self._make_feed_item(f"https://example.com/{i}") for i in range(_MAX_SEEN_URLS)]
        monitor._deduplicate(items)

        assert len(monitor._seen_urls_set) == _MAX_SEEN_URLS

        # Add one more - the first URL should be evicted
        new_items = [self._make_feed_item("https://example.com/new")]
        result = monitor._deduplicate(new_items)
        assert len(result) == 1

        # The first URL should now be evicted and can be re-added
        old_item = [self._make_feed_item("https://example.com/0")]
        result = monitor._deduplicate(old_item)
        assert len(result) == 1  # No longer seen, so it passes through

    def test_stats_property(self):
        """stats returns correct source count and items discovered."""
        queue = asyncio.Queue()
        mock_source = AsyncMock()
        mock_source.name = "test-src"
        monitor = ThunderMonitor(output_queue=queue, sources=[mock_source])

        stats = monitor.stats
        assert stats["sources_count"] == 1
        assert stats["items_discovered"] == 0
        assert stats["seen_urls_count"] == 0

    def test_stats_after_deduplicate(self):
        """stats reflects seen URLs count after deduplication."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue)

        items = [self._make_feed_item(f"https://example.com/{i}") for i in range(5)]
        monitor._deduplicate(items)

        assert monitor.stats["seen_urls_count"] == 5

    async def test_start_creates_tasks(self):
        """start() starts sources and creates polling tasks."""
        queue = asyncio.Queue()
        mock_source = AsyncMock()
        mock_source.name = "src1"
        mock_source._config = MagicMock()
        mock_source._config.poll_interval_seconds = 1
        mock_source.poll = AsyncMock(return_value=[])

        monitor = ThunderMonitor(output_queue=queue, sources=[mock_source])
        await monitor.start()

        # Source should have been started
        mock_source.start.assert_called_once()
        # Tasks should have been created
        assert len(monitor._tasks) == 1
        assert monitor._running is True

        # Clean up
        await monitor.stop()

    async def test_stop_cancels_tasks_and_stops_sources(self):
        """stop() cancels tasks and stops all sources."""
        queue = asyncio.Queue()
        mock_source = AsyncMock()
        mock_source.name = "src1"
        mock_source._config = MagicMock()
        mock_source._config.poll_interval_seconds = 1
        mock_source.poll = AsyncMock(return_value=[])

        monitor = ThunderMonitor(output_queue=queue, sources=[mock_source])
        await monitor.start()
        await monitor.stop()

        mock_source.stop.assert_called_once()
        assert monitor._running is False
        assert len(monitor._tasks) == 0

    async def test_start_when_already_running(self):
        """start() is a no-op if already running."""
        queue = asyncio.Queue()
        mock_source = AsyncMock()
        mock_source.name = "src1"
        mock_source._config = MagicMock()
        mock_source._config.poll_interval_seconds = 1
        mock_source.poll = AsyncMock(return_value=[])

        monitor = ThunderMonitor(output_queue=queue, sources=[mock_source])
        await monitor.start()
        await monitor.start()  # Second call should be no-op

        # Source start only called once
        assert mock_source.start.call_count == 1

        await monitor.stop()

    async def test_stop_when_not_running(self):
        """stop() is a no-op if not running."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue)
        await monitor.stop()  # Should not raise

    async def test_poll_source_puts_items_in_queue(self):
        """_poll_source puts discovered items into output_queue."""
        queue = asyncio.Queue()
        item = self._make_feed_item("https://example.com/discovered")

        mock_source = AsyncMock()
        mock_source.name = "poller"
        mock_source._config = MagicMock()
        mock_source._config.poll_interval_seconds = 100
        mock_source.poll = AsyncMock(return_value=[item])

        monitor = ThunderMonitor(output_queue=queue, sources=[mock_source])
        monitor._running = True

        # Run _poll_source but cancel after first iteration
        task = asyncio.create_task(monitor._poll_source(mock_source))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Item should be in the queue
        assert not queue.empty()
        queued_item = queue.get_nowait()
        assert queued_item.url == "https://example.com/discovered"
        assert monitor._items_discovered == 1

    async def test_poll_source_deduplicates(self):
        """_poll_source deduplicates items across polls."""
        queue = asyncio.Queue()
        item = self._make_feed_item("https://example.com/dup")

        call_count = 0

        async def poll_side_effect():
            nonlocal call_count
            call_count += 1
            return [item]

        mock_source = AsyncMock()
        mock_source.name = "dedup-src"
        mock_source._config = MagicMock()
        mock_source._config.poll_interval_seconds = 0.01
        mock_source.poll = AsyncMock(side_effect=poll_side_effect)

        monitor = ThunderMonitor(output_queue=queue, sources=[mock_source])
        monitor._running = True

        task = asyncio.create_task(monitor._poll_source(mock_source))
        # Let it run a few iterations
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Despite multiple polls, only 1 item should be in queue (dedup)
        assert monitor._items_discovered == 1

    async def test_add_source_while_running(self):
        """add_source() starts and polls a new source when monitor is running."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue, sources=[])

        # Manually set running without starting
        monitor._running = True

        new_source = AsyncMock()
        new_source.name = "dynamic"
        new_source._config = MagicMock()
        new_source._config.poll_interval_seconds = 100
        new_source.poll = AsyncMock(return_value=[])

        await monitor.add_source(new_source)

        assert len(monitor._sources) == 1
        new_source.start.assert_called_once()
        assert len(monitor._tasks) == 1

        # Clean up
        monitor._running = False
        for task in monitor._tasks:
            task.cancel()
        await asyncio.gather(*monitor._tasks, return_exceptions=True)

    async def test_add_source_while_not_running(self):
        """add_source() only appends source if monitor is not running."""
        queue = asyncio.Queue()
        monitor = ThunderMonitor(output_queue=queue, sources=[])

        new_source = AsyncMock()
        new_source.name = "static"

        await monitor.add_source(new_source)

        assert len(monitor._sources) == 1
        new_source.start.assert_not_called()
        assert len(monitor._tasks) == 0
