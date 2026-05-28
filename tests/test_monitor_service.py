"""Tests for src/core/monitor_service.py — MonitorService state management."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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


class TestMonitorServiceTwoStageScoring:
    """Tests for two-stage scoring: quick title score then async full score."""

    @patch("feedparser.parse")
    @patch("httpx.AsyncClient")
    def test_fetch_feeds_items_have_status_field(self, mock_client_cls, mock_feedparser_parse):
        """Items produced by fetch_feeds() have a 'status' field set to 'quick_scored'."""
        import asyncio

        service = MonitorService()
        service._feeds = [{"name": "Test", "url": "https://example.com/feed"}]
        service._auto_score = True

        # Mock HTTP response
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<rss></rss>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # Mock feedparser
        entry = MagicMock()
        entry.get = lambda k, d="": {"link": "https://example.com/1", "title": "Test Article"}.get(k, d)
        mock_parsed = MagicMock()
        mock_parsed.entries = [entry]
        mock_feedparser_parse.return_value = mock_parsed

        # Suppress background full-score tasks
        with patch.object(service, "_full_score_item", new_callable=AsyncMock):
            asyncio.run(service.fetch_feeds())

        assert len(service._recent_items) == 1
        item = service._recent_items[0]
        assert item["status"] == "quick_scored"

    @patch("feedparser.parse")
    @patch("httpx.AsyncClient")
    def test_fetch_feeds_items_have_quick_score_field(self, mock_client_cls, mock_feedparser_parse):
        """Items produced by fetch_feeds() have a 'quick_score' field."""
        import asyncio

        service = MonitorService()
        service._feeds = [{"name": "Test", "url": "https://example.com/feed"}]
        service._auto_score = True

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = "<rss></rss>"
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        entry = MagicMock()
        entry.get = lambda k, d="": {"link": "https://example.com/2", "title": "Article Title"}.get(k, d)
        mock_parsed = MagicMock()
        mock_parsed.entries = [entry]
        mock_feedparser_parse.return_value = mock_parsed

        # Suppress background full-score tasks
        with patch.object(service, "_full_score_item", new_callable=AsyncMock):
            asyncio.run(service.fetch_feeds())

        item = service._recent_items[0]
        assert "quick_score" in item
        assert item["quick_score"] is not None
        assert isinstance(item["quick_score"], float)
        assert item["score"] == item["quick_score"]

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    async def test_full_score_item_updates_status(self, mock_extract, mock_score):
        """_full_score_item updates item status to 'fully_scored' on success."""
        service = MonitorService()
        service._dispatcher = {
            "in_flight": 0, "max_in_flight": 10, "queue_size": 0,
            "total_scored": 0, "total_failed": 0, "total_retried": 0,
        }

        mock_content = MagicMock()
        mock_content.text = "Full article content"
        mock_extract.return_value = mock_content

        mock_result = MagicMock()
        mock_result.overall_score = 85.0
        mock_score.return_value = mock_result

        item_data = {
            "title": "Test",
            "link": "https://example.com/article",
            "source": "Test Feed",
            "fetched_at": "2025-01-01T00:00:00",
            "score": 50.0,
            "quick_score": 50.0,
            "full_score": None,
            "status": "quick_scored",
        }

        await service._full_score_item(item_data)

        assert item_data["status"] == "fully_scored"
        assert item_data["full_score"] == 85.0
        assert item_data["score"] == 85.0
        assert service._dispatcher["total_scored"] == 1

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    async def test_full_score_item_handles_extraction_failure(self, mock_extract, mock_score):
        """_full_score_item keeps quick_scored status when extraction fails."""
        service = MonitorService()
        service._dispatcher = {
            "in_flight": 0, "max_in_flight": 10, "queue_size": 0,
            "total_scored": 0, "total_failed": 0, "total_retried": 0,
        }

        mock_extract.side_effect = Exception("Network error")

        item_data = {
            "title": "Test",
            "link": "https://example.com/fail",
            "source": "Test Feed",
            "fetched_at": "2025-01-01T00:00:00",
            "score": 50.0,
            "quick_score": 50.0,
            "full_score": None,
            "status": "quick_scored",
        }

        await service._full_score_item(item_data)

        assert item_data["status"] == "quick_scored"
        assert item_data["full_score"] is None
        assert item_data["score"] == 50.0
        assert service._dispatcher["total_failed"] == 1

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    async def test_full_score_item_handles_scoring_failure(self, mock_extract, mock_score):
        """_full_score_item keeps quick_scored status when scorer fails."""
        service = MonitorService()
        service._dispatcher = {
            "in_flight": 0, "max_in_flight": 10, "queue_size": 0,
            "total_scored": 0, "total_failed": 0, "total_retried": 0,
        }

        mock_content = MagicMock()
        mock_content.text = "Some content"
        mock_extract.return_value = mock_content
        mock_score.side_effect = Exception("LLM timeout")

        item_data = {
            "title": "Test",
            "link": "https://example.com/score-fail",
            "source": "Test Feed",
            "fetched_at": "2025-01-01T00:00:00",
            "score": 45.0,
            "quick_score": 45.0,
            "full_score": None,
            "status": "quick_scored",
        }

        await service._full_score_item(item_data)

        assert item_data["status"] == "quick_scored"
        assert item_data["full_score"] is None
        assert item_data["score"] == 45.0
        assert service._dispatcher["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_full_score_item_skips_empty_link(self):
        """_full_score_item returns immediately if link is empty."""
        service = MonitorService()
        service._dispatcher = {
            "in_flight": 0, "max_in_flight": 10, "queue_size": 0,
            "total_scored": 0, "total_failed": 0, "total_retried": 0,
        }

        item_data = {
            "title": "Test",
            "link": "",
            "source": "Test Feed",
            "fetched_at": "2025-01-01T00:00:00",
            "score": 50.0,
            "quick_score": 50.0,
            "full_score": None,
            "status": "quick_scored",
        }

        await service._full_score_item(item_data)

        # Nothing should change
        assert item_data["status"] == "quick_scored"
        assert service._dispatcher["total_scored"] == 0
        assert service._dispatcher["total_failed"] == 0
