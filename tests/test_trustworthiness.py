"""Tests for FEAT-004: Trustworthiness Layer.

Tests dual-score display, divergence warning, evidence chain, RSS monitor service,
and monitor stats endpoint with real data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.core.monitor_service import MonitorService

# Sample RSS XML for mocking feed responses
SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Test Feed</title>
<item><title>Test Article One</title><link>https://example.com/1</link><description>Test content one</description></item>
<item><title>Test Article Two</title><link>https://example.com/2</link><description>Test content two</description></item>
<item><title>Scam Article 日入过万 躺赚 财富自由</title><link>https://example.com/3</link><description>Scam content</description></item>
</channel>
</rss>"""


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


class TestDualScoreDisplay:
    """Tests for dual-score (rule vs LLM) display in result page."""

    def test_dual_score_display_junk_text(self, web_client, sample_junk_text):
        """Score junk text (rules fire) should produce result_data with rule_score and llm_score."""
        with patch("src.core.scorer.score") as mock_score:
            from src.models.score import DimensionScores, ScoreResult

            mock_result = ScoreResult(
                overall_score=25.0,
                dimensions=DimensionScores(
                    originality=10,
                    info_density=5,
                    reasoning_quality=10,
                    readability=30,
                    timeliness=20,
                    ai_generated_prob=20,
                    emotional_manipulation=80,
                    advertorial_prob=70,
                    scam_prob=95,
                ),
                labels=["疑似骗局"],
                summary="This is scam content",
                confidence=0.9,
                model_used="test",
                cost=0.001,
                rule_hits=["scam_keywords", "emotional_anxiety_phrases"],
                dimension_sources={"scam_prob": "rule", "emotional_manipulation": "rule"},
            )
            mock_score.return_value = mock_result

            response = web_client.post(
                "/score-submit",
                data={"input_type": "text", "text": sample_junk_text},
                headers={"HX-Request": "true"},
            )

            assert response.status_code == 200
            html = response.text
            # Dual score rings should be present
            assert "规则引擎" in html
            assert "综合评分" in html

    def test_divergence_warning_present(self, web_client, sample_junk_text):
        """When rule_score and llm_score differ by >20, show divergence warning."""
        with patch("src.core.scorer.score") as mock_score:
            from src.models.score import DimensionScores, ScoreResult

            # LLM gives a high score but rules will give low score for scam text
            mock_result = ScoreResult(
                overall_score=75.0,
                dimensions=DimensionScores(
                    originality=80,
                    info_density=70,
                    reasoning_quality=75,
                    readability=80,
                    timeliness=60,
                    ai_generated_prob=10,
                    emotional_manipulation=5,
                    advertorial_prob=5,
                    scam_prob=5,
                ),
                labels=[],
                summary="High quality content",
                confidence=0.85,
                model_used="test",
                cost=0.001,
                rule_hits=["scam_keywords"],
                dimension_sources={},
            )
            mock_score.return_value = mock_result

            response = web_client.post(
                "/score-submit",
                data={"input_type": "text", "text": sample_junk_text},
                headers={"HX-Request": "true"},
            )

            assert response.status_code == 200
            html = response.text
            assert "规则与AI评分差异较大" in html

    def test_no_divergence_warning_close_scores(self, web_client, sample_good_text):
        """When scores are close (no rules fire), no divergence warning shown."""
        with patch("src.core.scorer.score") as mock_score:
            from src.models.score import DimensionScores, ScoreResult

            mock_result = ScoreResult(
                overall_score=72.0,
                dimensions=DimensionScores(
                    originality=75,
                    info_density=70,
                    reasoning_quality=72,
                    readability=80,
                    timeliness=60,
                    ai_generated_prob=15,
                    emotional_manipulation=10,
                    advertorial_prob=5,
                    scam_prob=5,
                ),
                labels=[],
                summary="Good quality content",
                confidence=0.85,
                model_used="test",
                cost=0.001,
                rule_hits=[],
                dimension_sources={},
            )
            mock_score.return_value = mock_result

            response = web_client.post(
                "/score-submit",
                data={"input_type": "text", "text": sample_good_text},
                headers={"HX-Request": "true"},
            )

            assert response.status_code == 200
            html = response.text
            # No divergence warning
            assert "规则与AI评分差异较大" not in html


class TestEvidenceChain:
    """Tests for evidence chain section in result template."""

    def test_evidence_chain_in_template(self, web_client, sample_junk_text):
        """Verify evidence chain section appears in result when rules fire."""
        with patch("src.core.scorer.score") as mock_score:
            from src.models.score import DimensionScores, ScoreResult

            mock_result = ScoreResult(
                overall_score=20.0,
                dimensions=DimensionScores(
                    originality=10,
                    info_density=5,
                    reasoning_quality=10,
                    readability=30,
                    timeliness=20,
                    ai_generated_prob=20,
                    emotional_manipulation=85,
                    advertorial_prob=70,
                    scam_prob=95,
                ),
                labels=["疑似骗局"],
                summary="This content contains scam patterns",
                confidence=0.95,
                model_used="test",
                cost=0.001,
                rule_hits=["scam_keywords", "emotional_anxiety_phrases"],
                dimension_sources={"scam_prob": "rule", "emotional_manipulation": "rule"},
            )
            mock_score.return_value = mock_result

            response = web_client.post(
                "/score-submit",
                data={"input_type": "text", "text": sample_junk_text},
                headers={"HX-Request": "true"},
            )

            assert response.status_code == 200
            html = response.text
            # Evidence chain section title
            assert "判定依据" in html
            # Triggered rules section
            assert "触发规则" in html
            assert "scam_keywords" in html
            # Keyword matches section removed in Round 9 (redundant)
            # LLM assessment
            assert "AI评估摘要" in html
            # Confidence factors
            assert "置信度因子" in html


class TestRSSMonitorFetch:
    """Tests for MonitorService RSS feed fetching."""

    @pytest.mark.asyncio
    async def test_rss_monitor_fetch(self):
        """Mock httpx response with valid RSS XML, call fetch_feeds(), verify items parsed."""
        service = MonitorService()
        service._feeds = [{"url": "https://example.com/feed.xml", "name": "Test Feed"}]
        service._auto_score = True

        mock_response = AsyncMock()
        mock_response.text = SAMPLE_RSS_XML
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(service, "_full_score_item", new_callable=AsyncMock):
                await service.fetch_feeds()

        # Should have discovered 3 items
        assert service._thunder["items_discovered"] == 3
        assert service._thunder["seen_urls_count"] == 3
        assert len(service._recent_items) == 3

        # Check items have expected fields
        first_item = service._recent_items[0]
        assert "title" in first_item
        assert "link" in first_item
        assert "source" in first_item
        assert first_item["source"] == "Test Feed"

    @pytest.mark.asyncio
    async def test_rss_monitor_deduplication(self):
        """Fetching same feed twice should not duplicate items."""
        service = MonitorService()
        service._feeds = [{"url": "https://example.com/feed.xml", "name": "Test Feed"}]
        service._auto_score = False

        mock_response = AsyncMock()
        mock_response.text = SAMPLE_RSS_XML
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await service.fetch_feeds()
            await service.fetch_feeds()

        # Still only 3 items (no duplicates)
        assert service._thunder["items_discovered"] == 3
        assert len(service._recent_items) == 3

    @pytest.mark.asyncio
    async def test_rss_monitor_auto_scoring(self):
        """When auto_score is True, items get scored using rules."""
        service = MonitorService()
        service._feeds = [{"url": "https://example.com/feed.xml", "name": "Test Feed"}]
        service._auto_score = True

        mock_response = AsyncMock()
        mock_response.text = SAMPLE_RSS_XML
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch.object(service, "_full_score_item", new_callable=AsyncMock):
                await service.fetch_feeds()

        # Each item should have a quick_score from rules-only scoring
        for item in service._recent_items:
            assert item["score"] is not None
            assert 0 <= item["score"] <= 100
            assert item["quick_score"] is not None
            assert item["status"] == "quick_scored"


class TestRSSMonitorStartStop:
    """Tests for MonitorService start/stop lifecycle."""

    def test_start_sets_running_and_loads_feeds(self):
        """start() sets running state and loads feed config."""
        service = MonitorService()
        service.start()
        assert service.is_running is True
        assert service._thunder["sources_count"] > 0

    def test_stop_cancels_running(self):
        """stop() sets running to False."""
        service = MonitorService()
        service.start()
        service.stop()
        assert service.is_running is False

    def test_start_stop_lifecycle(self):
        """Start then stop maintains stats from last state."""
        service = MonitorService()
        service.start()
        sources_count = service._thunder["sources_count"]
        service.stop()
        assert service._thunder["sources_count"] == sources_count


class TestRSSMonitorStats:
    """Tests for MonitorService.get_stats() with real data."""

    @pytest.mark.asyncio
    async def test_monitor_stats_after_fetch(self):
        """After fetch, get_stats() returns real counts and recent items."""
        service = MonitorService()
        service._feeds = [{"url": "https://example.com/feed.xml", "name": "Test Feed"}]
        service._auto_score = False

        mock_response = AsyncMock()
        mock_response.text = SAMPLE_RSS_XML
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await service.fetch_feeds()

        stats = service.get_stats()
        assert stats["thunder"]["items_discovered"] == 3
        assert stats["thunder"]["seen_urls_count"] == 3
        assert "recent_items" in stats
        assert len(stats["recent_items"]) == 3
        assert "feeds" in stats
        assert stats["last_fetch_time"] is not None

    def test_stats_has_feeds_field(self):
        """get_stats() includes feeds and recent_items fields."""
        service = MonitorService()
        stats = service.get_stats()
        assert "recent_items" in stats
        assert "feeds" in stats
        assert "last_fetch_time" in stats


class TestMonitorStatsEndpointWithItems:
    """Tests for the HTMX partial returning item data."""

    @pytest.mark.asyncio
    async def test_monitor_stats_endpoint_shows_items(self, web_client):
        """After fetching feeds, the monitor-stats partial shows recent items."""
        service = MonitorService()
        service._feeds = [{"url": "https://example.com/feed.xml", "name": "Test Feed"}]
        service._auto_score = False

        mock_response = AsyncMock()
        mock_response.text = SAMPLE_RSS_XML
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await service.fetch_feeds()

        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200
        html = response.text
        # Should show recent items table
        assert "最近抓取" in html
        assert "Test Article" in html

    def test_monitor_stats_endpoint_shows_feeds(self, web_client):
        """Monitor stats partial shows configured feeds when started."""
        service = MonitorService()
        service.start()

        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200
        html = response.text
        # Should show feed info
        assert "RSS 信源" in html
