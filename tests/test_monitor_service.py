"""Tests for src/monitor/service.py — MonitorService unit tests."""

from __future__ import annotations

from pathlib import Path

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
