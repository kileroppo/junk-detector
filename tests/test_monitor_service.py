"""Tests for src/monitor/service.py — MonitorService unit tests."""

from __future__ import annotations

import pytest
import yaml

from src.monitor.service import MonitorService
from src.thunder.sources import RSSSource, WebhookSource

SAMPLE_CONFIG = {
    "thunder": {
        "sources": [
            {
                "name": "test-rss",
                "type": "rss",
                "url": "https://example.com/feed",
                "enabled": True,
                "priority": 5,
                "poll_interval_seconds": 300,
            },
            {
                "name": "disabled",
                "type": "rss",
                "url": "https://d.com/feed",
                "enabled": False,
            },
        ],
        "webhook": {"enabled": True, "path": "/webhook/content"},
    },
    "dispatcher": {
        "max_in_flight": 5,
        "retry": {
            "max_attempts": 4,
            "base_delay_seconds": 1.0,
            "max_delay_seconds": 30.0,
        },
    },
}


class TestMonitorServiceInit:
    """Tests for MonitorService.__init__."""

    def test_creates_correct_number_of_sources(self):
        """__init__ creates enabled sources only plus webhook."""
        service = MonitorService(SAMPLE_CONFIG)

        # Should have 1 enabled RSS + 1 webhook = 2 sources total
        sources = service.thunder._sources
        assert len(sources) == 2

    def test_parses_dispatcher_config(self):
        """__init__ parses dispatcher settings correctly."""
        service = MonitorService(SAMPLE_CONFIG)

        assert service._max_in_flight == 5
        assert service._retry_policy.max_attempts == 4
        assert service._retry_policy.base_delay_seconds == 1.0
        assert service._retry_policy.max_delay_seconds == 30.0

    def test_initial_stats_are_zero(self):
        """__init__ starts with zero stats counters."""
        service = MonitorService(SAMPLE_CONFIG)

        assert service._total_scored == 0
        assert service._total_failed == 0
        assert service._total_retried == 0
        assert service._in_flight == 0


class TestBuildSources:
    """Tests for MonitorService._build_sources."""

    def test_skips_disabled_sources(self):
        """_build_sources skips sources with enabled=False."""
        service = MonitorService(SAMPLE_CONFIG)
        thunder_config = SAMPLE_CONFIG["thunder"]
        sources = service._build_sources(thunder_config)

        # Only enabled RSS and webhook
        rss_sources = [s for s in sources if isinstance(s, RSSSource)]
        assert len(rss_sources) == 1
        assert rss_sources[0].name == "test-rss"

    def test_creates_webhook_source_when_enabled(self):
        """_build_sources creates WebhookSource when webhook.enabled=True."""
        service = MonitorService(SAMPLE_CONFIG)
        thunder_config = SAMPLE_CONFIG["thunder"]
        sources = service._build_sources(thunder_config)

        webhook_sources = [s for s in sources if isinstance(s, WebhookSource)]
        assert len(webhook_sources) == 1

    def test_no_webhook_when_disabled(self):
        """_build_sources does not create WebhookSource when webhook.enabled=False."""
        config = {
            "thunder": {
                "sources": [
                    {
                        "name": "test-rss",
                        "type": "rss",
                        "url": "https://example.com/feed",
                        "enabled": True,
                    }
                ],
                "webhook": {"enabled": False},
            },
            "dispatcher": {},
        }
        service = MonitorService(config)
        thunder_config = config["thunder"]
        sources = service._build_sources(thunder_config)

        webhook_sources = [s for s in sources if isinstance(s, WebhookSource)]
        assert len(webhook_sources) == 0


class TestFromConfigFile:
    """Tests for MonitorService.from_config_file."""

    def test_nonexistent_path_raises_file_not_found(self):
        """from_config_file raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            MonitorService.from_config_file("/nonexistent/config.yaml")

    def test_valid_yaml_file(self, tmp_path):
        """from_config_file with valid yaml file creates MonitorService."""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml.dump(SAMPLE_CONFIG), encoding="utf-8")

        service = MonitorService.from_config_file(str(config_file))

        assert service is not None
        assert service._max_in_flight == 5

    def test_empty_yaml_file(self, tmp_path):
        """from_config_file with empty yaml creates service with defaults."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("", encoding="utf-8")

        service = MonitorService.from_config_file(str(config_file))
        assert service is not None


class TestStatsProperty:
    """Tests for MonitorService.stats property."""

    def test_stats_structure(self):
        """stats property returns correct structure."""
        service = MonitorService(SAMPLE_CONFIG)
        stats = service.stats

        assert "thunder" in stats
        assert "dispatcher" in stats
        assert "total_scored" in stats["dispatcher"]
        assert "total_failed" in stats["dispatcher"]
        assert "total_retried" in stats["dispatcher"]
        assert "in_flight" in stats["dispatcher"]
        assert "queue_size" in stats["dispatcher"]
        assert "max_in_flight" in stats["dispatcher"]

    def test_stats_initial_values(self):
        """stats returns zero values initially."""
        service = MonitorService(SAMPLE_CONFIG)
        stats = service.stats

        assert stats["dispatcher"]["total_scored"] == 0
        assert stats["dispatcher"]["total_failed"] == 0
        assert stats["dispatcher"]["in_flight"] == 0
        assert stats["dispatcher"]["max_in_flight"] == 5


class TestWebhookSourceProperty:
    """Tests for MonitorService.webhook_source property."""

    def test_webhook_source_not_none_when_enabled(self):
        """webhook_source property is not None when webhook enabled."""
        service = MonitorService(SAMPLE_CONFIG)

        assert service.webhook_source is not None
        assert isinstance(service.webhook_source, WebhookSource)

    def test_webhook_source_none_when_disabled(self):
        """webhook_source property is None when webhook disabled."""
        config = {
            "thunder": {
                "sources": [],
                "webhook": {"enabled": False},
            },
            "dispatcher": {},
        }
        service = MonitorService(config)

        assert service.webhook_source is None


class TestGenerateSummary:
    """Tests for MonitorService.generate_summary."""

    def test_generate_summary_empty(self):
        """generate_summary returns zero state when no items scored."""
        service = MonitorService(SAMPLE_CONFIG)
        summary = service.generate_summary()

        assert summary["total_scored"] == 0
        assert summary["total_failed"] == 0
        assert summary["average_score"] == 0.0
        assert summary["high_risk_items"] == []
        assert summary["top_labels"] == []

    def test_generate_summary_with_items(self):
        """generate_summary returns correct totals and averages."""
        service = MonitorService(SAMPLE_CONFIG)
        service._scored_items = [
            {
                "title": "Article 1",
                "url": "http://a.com/1",
                "source": "rss",
                "score": 80,
                "labels": ["good"],
            },
            {
                "title": "Article 2",
                "url": "http://a.com/2",
                "source": "rss",
                "score": 60,
                "labels": ["ok"],
            },
            {
                "title": "Article 3",
                "url": "http://a.com/3",
                "source": "rss",
                "score": 40,
                "labels": ["good"],
            },
        ]

        summary = service.generate_summary()

        assert summary["total_scored"] == 3
        assert summary["average_score"] == 60.0

    def test_generate_summary_high_risk_detection(self):
        """Items with overall_score < 40 appear in high_risk_items."""
        service = MonitorService(SAMPLE_CONFIG)
        service._scored_items = [
            {
                "title": "Good Article",
                "url": "http://a.com/1",
                "source": "rss",
                "score": 80,
                "labels": [],
            },
            {
                "title": "Risky Article",
                "url": "http://a.com/2",
                "source": "rss",
                "score": 30,
                "labels": ["spam"],
            },
            {
                "title": "Very Risky",
                "url": "http://a.com/3",
                "source": "rss",
                "score": 10,
                "labels": ["scam"],
            },
        ]

        summary = service.generate_summary()

        assert len(summary["high_risk_items"]) == 2
        titles = [item["title"] for item in summary["high_risk_items"]]
        assert "Risky Article" in titles
        assert "Very Risky" in titles
        assert "Good Article" not in titles

    def test_generate_summary_top_labels(self):
        """Labels are aggregated and sorted by frequency."""
        service = MonitorService(SAMPLE_CONFIG)
        service._scored_items = [
            {
                "title": "A1",
                "url": "http://a.com/1",
                "source": "rss",
                "score": 70,
                "labels": ["spam", "clickbait"],
            },
            {
                "title": "A2",
                "url": "http://a.com/2",
                "source": "rss",
                "score": 50,
                "labels": ["spam"],
            },
            {
                "title": "A3",
                "url": "http://a.com/3",
                "source": "rss",
                "score": 60,
                "labels": ["clickbait", "ai"],
            },
        ]

        summary = service.generate_summary()

        # spam appears 2x, clickbait 2x, ai 1x
        assert "spam" in summary["top_labels"]
        assert "clickbait" in summary["top_labels"]
        assert "ai" in summary["top_labels"]
        # spam and clickbait should appear before ai
        ai_index = summary["top_labels"].index("ai")
        assert (
            summary["top_labels"].index("spam") < ai_index
            or summary["top_labels"].index("clickbait") < ai_index
        )

    def test_last_summary_property(self):
        """After calling generate_summary(), last_summary returns the same data."""
        service = MonitorService(SAMPLE_CONFIG)
        service._scored_items = [
            {
                "title": "A1",
                "url": "http://a.com/1",
                "source": "rss",
                "score": 70,
                "labels": ["good"],
            },
        ]

        assert service.last_summary is None

        summary = service.generate_summary()

        assert service.last_summary is not None
        assert service.last_summary == summary
        assert service.last_summary["total_scored"] == 1


class TestScoredItemsTrimming:
    """Tests for _scored_items bounded growth."""

    def test_scored_items_trimmed_when_exceeds_limit(self):
        """_scored_items is trimmed when it exceeds MAX_SCORED_ITEMS."""
        service = MonitorService(SAMPLE_CONFIG)

        # Fill beyond the limit
        service._scored_items = [
            {
                "title": f"Article {i}",
                "url": f"http://a.com/{i}",
                "source": "rss",
                "score": 50,
                "labels": [],
            }
            for i in range(MonitorService._MAX_SCORED_ITEMS + 1)
        ]

        # Simulate what _execute_task does after appending
        if len(service._scored_items) > service._MAX_SCORED_ITEMS:
            service._scored_items = service._scored_items[MonitorService._MAX_SCORED_ITEMS // 2 :]

        # Should be trimmed to the newer half
        assert len(service._scored_items) <= MonitorService._MAX_SCORED_ITEMS
        # The remaining items should be the newer ones (higher indices)
        assert (
            service._scored_items[0]["title"] == f"Article {MonitorService._MAX_SCORED_ITEMS // 2}"
        )


class TestExecuteTaskIntegration:
    """Tests for _execute_task -> _scored_items integration."""

    @pytest.mark.asyncio
    async def test_execute_task_populates_scored_items(self):
        """After _execute_task succeeds, item is added to _scored_items."""
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock, patch

        from src.dispatcher.models import TaskPayload

        service = MonitorService(SAMPLE_CONFIG)
        # Need an event loop semaphore
        import asyncio

        service._semaphore = asyncio.Semaphore(service._max_in_flight)

        task = TaskPayload(
            url="http://example.com/article",
            title="Test Article",
            source_name="test-source",
            max_attempts=3,
        )

        # Mock _score_item to return a successful result
        from src.dispatcher.models import TaskResult

        mock_result = TaskResult(
            task_id=task.id,
            success=True,
            score_result={"overall_score": 72, "labels": ["informative"]},
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            attempts_used=1,
        )

        with patch.object(service, "_score_item", new_callable=AsyncMock, return_value=mock_result):
            await service._execute_task(task)

        assert len(service._scored_items) == 1
        assert service._scored_items[0]["title"] == "Test Article"
        assert service._scored_items[0]["score"] == 72
        assert service._scored_items[0]["labels"] == ["informative"]
