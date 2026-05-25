"""Tests for the side_effects module: base, notification, stats_collector."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.pipeline import PipelineContext
from src.core.side_effects.base import SideEffect, SideEffectRunner
from src.core.side_effects.notification import NotificationSideEffect
from src.core.side_effects.stats_collector import StatsCollectorSideEffect
from src.models.score import Content, DimensionScores, InputType, ScoreResult

# ===== Fixtures =====


def _make_dimensions(**overrides) -> DimensionScores:
    defaults = {
        "originality": 50,
        "info_density": 40,
        "reasoning_quality": 60,
        "readability": 70,
        "timeliness": 50,
        "ai_generated_prob": 20,
        "emotional_manipulation": 30,
        "advertorial_prob": 25,
        "scam_prob": 10,
    }
    defaults.update(overrides)
    return DimensionScores(**defaults)


def _make_result(overall_score: float = 65, labels: list[str] | None = None) -> ScoreResult:
    return ScoreResult(
        overall_score=overall_score,
        dimensions=_make_dimensions(),
        labels=labels or ["test_label"],
        summary="test summary",
        model_used="test-model",
    )


def _make_content(
    source_url: str = "https://example.com/article",
    title: str = "Test Article",
    text: str = "This is test content for scoring.",
) -> Content:
    content = Content(
        input_type=InputType.TEXT,
        text=text,
        source_url=source_url,
        title=title,
    )
    content.compute_hash()
    return content


def _make_context(
    overall_score: float = 65,
    labels: list[str] | None = None,
    source_url: str = "https://example.com/article",
    with_result: bool = True,
) -> PipelineContext:
    ctx = PipelineContext(raw_input="test", input_type="text")
    if with_result:
        ctx.result = _make_result(overall_score=overall_score, labels=labels)
        ctx.content = _make_content(source_url=source_url)
    return ctx


# ===== Concrete SideEffect for Testing Base =====


class DummySideEffect(SideEffect):
    """A simple side effect for testing the runner."""

    def __init__(
        self,
        name: str = "dummy",
        should_fire: bool = True,
        raise_on_execute: bool = False,
        raise_on_trigger: bool = False,
    ):
        self._name = name
        self._should_fire = should_fire
        self._raise_on_execute = raise_on_execute
        self._raise_on_trigger = raise_on_trigger
        self.executed = False

    @property
    def name(self) -> str:
        return self._name

    async def should_trigger(self, ctx: PipelineContext) -> bool:
        if self._raise_on_trigger:
            raise RuntimeError("trigger error")
        return self._should_fire

    async def execute(self, ctx: PipelineContext) -> None:
        if self._raise_on_execute:
            raise RuntimeError("execute error")
        self.executed = True


# ===== SideEffectRunner Tests =====


class TestSideEffectRunner:
    """Tests for the SideEffectRunner base class."""

    async def test_register_adds_effects(self):
        runner = SideEffectRunner()
        effect = DummySideEffect()
        result = runner.register(effect)
        # Returns self for chaining
        assert result is runner
        assert effect in runner._effects

    async def test_register_multiple_effects(self):
        runner = SideEffectRunner()
        e1 = DummySideEffect(name="one")
        e2 = DummySideEffect(name="two")
        runner.register(e1).register(e2)
        assert len(runner._effects) == 2

    async def test_init_with_effects_list(self):
        e1 = DummySideEffect(name="one")
        e2 = DummySideEffect(name="two")
        runner = SideEffectRunner(effects=[e1, e2])
        assert len(runner._effects) == 2

    async def test_run_all_executes_triggered_effects(self):
        ctx = _make_context()
        e1 = DummySideEffect(name="yes", should_fire=True)
        e2 = DummySideEffect(name="no", should_fire=False)
        runner = SideEffectRunner(effects=[e1, e2])
        await runner.run_all(ctx)
        assert e1.executed is True
        assert e2.executed is False

    async def test_run_all_error_isolation_execute(self):
        """An effect that raises in execute does not crash the runner."""
        ctx = _make_context()
        bad = DummySideEffect(name="bad", raise_on_execute=True)
        good = DummySideEffect(name="good")
        runner = SideEffectRunner(effects=[bad, good])
        # Should not raise
        await runner.run_all(ctx)
        # The good effect still ran
        assert good.executed is True

    async def test_run_all_error_isolation_trigger(self):
        """An effect that raises in should_trigger does not crash the runner."""
        ctx = _make_context()
        bad = DummySideEffect(name="bad_trigger", raise_on_trigger=True)
        good = DummySideEffect(name="good")
        runner = SideEffectRunner(effects=[bad, good])
        # Should not raise
        await runner.run_all(ctx)
        # The good effect still executed
        assert good.executed is True

    async def test_run_all_no_effects(self):
        """Runner with no effects does nothing."""
        ctx = _make_context()
        runner = SideEffectRunner()
        await runner.run_all(ctx)  # Should not raise

    async def test_safe_execute_logs_on_failure(self, caplog):
        ctx = _make_context()
        bad = DummySideEffect(name="crasher", raise_on_execute=True)
        runner = SideEffectRunner(effects=[bad])
        with caplog.at_level(logging.ERROR, logger="side_effects"):
            await runner.run_all(ctx)
        assert "crasher" in caplog.text
        assert "failed" in caplog.text

    async def test_should_trigger_failure_logs_warning(self, caplog):
        ctx = _make_context()
        bad = DummySideEffect(name="trigger_crash", raise_on_trigger=True)
        runner = SideEffectRunner(effects=[bad])
        with caplog.at_level(logging.WARNING, logger="side_effects"):
            await runner.run_all(ctx)
        assert "trigger_crash" in caplog.text


# ===== NotificationSideEffect Tests =====


class TestNotificationSideEffect:
    """Tests for the NotificationSideEffect."""

    async def test_should_trigger_below_threshold(self):
        ctx = _make_context(overall_score=20)
        effect = NotificationSideEffect(threshold=30.0)
        assert await effect.should_trigger(ctx) is True

    async def test_should_trigger_at_threshold(self):
        ctx = _make_context(overall_score=30)
        effect = NotificationSideEffect(threshold=30.0)
        assert await effect.should_trigger(ctx) is False

    async def test_should_trigger_above_threshold(self):
        ctx = _make_context(overall_score=80)
        effect = NotificationSideEffect(threshold=30.0)
        assert await effect.should_trigger(ctx) is False

    async def test_should_trigger_no_result(self):
        ctx = _make_context(with_result=False)
        effect = NotificationSideEffect(threshold=30.0)
        assert await effect.should_trigger(ctx) is False

    async def test_name(self):
        effect = NotificationSideEffect()
        assert effect.name == "notification"

    async def test_execute_logs_warning(self, caplog):
        ctx = _make_context(overall_score=15, labels=["junk", "spam"])
        effect = NotificationSideEffect(threshold=30.0)
        with caplog.at_level(logging.WARNING, logger="side_effects.notification"):
            await effect.execute(ctx)
        assert "LOW QUALITY ALERT" in caplog.text
        assert "Test Article" in caplog.text
        assert "15" in caplog.text

    async def test_execute_logs_labels(self, caplog):
        ctx = _make_context(overall_score=15, labels=["junk", "spam"])
        effect = NotificationSideEffect(threshold=30.0)
        with caplog.at_level(logging.WARNING, logger="side_effects.notification"):
            await effect.execute(ctx)
        assert "junk" in caplog.text
        assert "spam" in caplog.text

    async def test_execute_with_webhook(self):
        ctx = _make_context(overall_score=15)
        effect = NotificationSideEffect(
            threshold=30.0, webhook_url="https://hooks.example.com/alert"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await effect.execute(ctx)

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://hooks.example.com/alert"
            payload = call_args[1]["json"]
            assert payload["event"] == "low_quality_alert"
            assert payload["title"] == "Test Article"
            assert payload["score"] == 15

    async def test_execute_webhook_error_logged(self, caplog):
        ctx = _make_context(overall_score=15)
        effect = NotificationSideEffect(
            threshold=30.0, webhook_url="https://hooks.example.com/alert"
        )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with caplog.at_level(logging.WARNING, logger="side_effects.notification"):
                await effect.execute(ctx)

            assert "Webhook delivery failed" in caplog.text

    async def test_execute_webhook_bad_status(self, caplog):
        ctx = _make_context(overall_score=15)
        effect = NotificationSideEffect(
            threshold=30.0, webhook_url="https://hooks.example.com/alert"
        )

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with caplog.at_level(logging.WARNING, logger="side_effects.notification"):
                await effect.execute(ctx)

            assert "500" in caplog.text

    async def test_execute_no_webhook_configured(self):
        ctx = _make_context(overall_score=15)
        effect = NotificationSideEffect(threshold=30.0, webhook_url=None)
        # Should not raise, no webhook call
        await effect.execute(ctx)

    async def test_execute_no_content(self, caplog):
        """Execute works even when content is None."""
        ctx = PipelineContext(raw_input="test", input_type="text")
        ctx.result = _make_result(overall_score=15)
        ctx.content = None
        effect = NotificationSideEffect(threshold=30.0)
        with caplog.at_level(logging.WARNING, logger="side_effects.notification"):
            await effect.execute(ctx)
        assert "Unknown" in caplog.text


# ===== StatsCollectorSideEffect Tests =====


class TestStatsCollectorSideEffect:
    """Tests for the StatsCollectorSideEffect."""

    async def test_name(self):
        effect = StatsCollectorSideEffect()
        assert effect.name == "stats_collector"

    async def test_should_trigger_with_result(self):
        ctx = _make_context()
        effect = StatsCollectorSideEffect()
        assert await effect.should_trigger(ctx) is True

    async def test_should_trigger_no_result(self):
        ctx = _make_context(with_result=False)
        effect = StatsCollectorSideEffect()
        assert await effect.should_trigger(ctx) is False

    async def test_execute_increments_total(self):
        ctx = _make_context(overall_score=70)
        effect = StatsCollectorSideEffect()
        await effect.execute(ctx)
        assert effect._total_scored == 1
        assert effect._total_score_sum == 70.0

    async def test_execute_multiple_scores(self):
        effect = StatsCollectorSideEffect()
        ctx1 = _make_context(overall_score=60)
        ctx2 = _make_context(overall_score=80)
        await effect.execute(ctx1)
        await effect.execute(ctx2)
        assert effect._total_scored == 2
        assert effect._total_score_sum == 140.0

    async def test_execute_tracks_source(self):
        ctx = _make_context(source_url="https://news.example.com/article1")
        effect = StatsCollectorSideEffect()
        await effect.execute(ctx)
        assert "news.example.com" in effect._source_scores
        assert effect._source_scores["news.example.com"] == [65]

    async def test_execute_tracks_multiple_sources(self):
        effect = StatsCollectorSideEffect()
        ctx1 = _make_context(overall_score=50, source_url="https://site-a.com/page")
        ctx2 = _make_context(overall_score=80, source_url="https://site-b.com/page")
        await effect.execute(ctx1)
        await effect.execute(ctx2)
        assert "site-a.com" in effect._source_scores
        assert "site-b.com" in effect._source_scores

    async def test_execute_unknown_source_when_no_url(self):
        ctx = PipelineContext(raw_input="test", input_type="text")
        ctx.result = _make_result(overall_score=55)
        ctx.content = Content(
            input_type=InputType.TEXT, text="no url content", source_url=None, title="No URL"
        )
        ctx.content.compute_hash()
        effect = StatsCollectorSideEffect()
        await effect.execute(ctx)
        assert "unknown" in effect._source_scores

    async def test_execute_tracks_labels(self):
        ctx = _make_context(labels=["junk", "spam"])
        effect = StatsCollectorSideEffect()
        await effect.execute(ctx)
        assert effect._label_counts["junk"] == 1
        assert effect._label_counts["spam"] == 1

    async def test_execute_accumulates_labels(self):
        effect = StatsCollectorSideEffect()
        ctx1 = _make_context(labels=["junk", "spam"])
        ctx2 = _make_context(labels=["junk", "low_quality"])
        await effect.execute(ctx1)
        await effect.execute(ctx2)
        assert effect._label_counts["junk"] == 2
        assert effect._label_counts["spam"] == 1
        assert effect._label_counts["low_quality"] == 1

    async def test_get_stats_correct(self):
        effect = StatsCollectorSideEffect()
        ctx1 = _make_context(overall_score=40, labels=["bad"], source_url="https://a.com/p")
        ctx2 = _make_context(overall_score=80, labels=["good"], source_url="https://b.com/p")
        await effect.execute(ctx1)
        await effect.execute(ctx2)

        stats = effect.get_stats()
        assert stats["total_scored"] == 2
        assert stats["avg_score"] == 60.0
        assert stats["label_frequency"] == {"bad": 1, "good": 1}
        assert "a.com" in stats["source_rankings"]
        assert "b.com" in stats["source_rankings"]
        assert stats["source_rankings"]["a.com"]["avg_score"] == 40.0
        assert stats["source_rankings"]["b.com"]["avg_score"] == 80.0
        assert stats["source_rankings"]["a.com"]["count"] == 1
        assert stats["source_rankings"]["a.com"]["min_score"] == 40.0
        assert stats["source_rankings"]["a.com"]["max_score"] == 40.0

    async def test_get_stats_empty(self):
        effect = StatsCollectorSideEffect()
        stats = effect.get_stats()
        assert stats["total_scored"] == 0
        assert stats["avg_score"] == 0

    async def test_get_stats_sorted_by_avg_ascending(self):
        effect = StatsCollectorSideEffect()
        ctx1 = _make_context(overall_score=80, source_url="https://good.com/p")
        ctx2 = _make_context(overall_score=20, source_url="https://bad.com/p")
        await effect.execute(ctx1)
        await effect.execute(ctx2)

        stats = effect.get_stats()
        sources = list(stats["source_rankings"].keys())
        # Worst (lowest avg score) first
        assert sources[0] == "bad.com"
        assert sources[1] == "good.com"

    async def test_reset_clears_state(self):
        effect = StatsCollectorSideEffect()
        ctx = _make_context(labels=["test"])
        await effect.execute(ctx)
        assert effect._total_scored == 1

        effect.reset()
        assert effect._total_scored == 0
        assert effect._total_score_sum == 0.0
        assert len(effect._source_scores) == 0
        assert len(effect._label_counts) == 0

    async def test_reset_updates_last_reset(self):

        effect = StatsCollectorSideEffect()
        old_reset = effect._last_reset
        # Small delay to ensure time difference
        effect.reset()
        assert effect._last_reset >= old_reset

    async def test_get_stats_includes_since(self):
        effect = StatsCollectorSideEffect()
        stats = effect.get_stats()
        assert "since" in stats
        # Should be an ISO format string
        assert "T" in stats["since"]

    async def test_execute_no_content(self):
        """Execute handles missing content gracefully."""
        ctx = PipelineContext(raw_input="test", input_type="text")
        ctx.result = _make_result(overall_score=55)
        ctx.content = None
        effect = StatsCollectorSideEffect()
        await effect.execute(ctx)
        assert "unknown" in effect._source_scores

    async def test_execute_invalid_url_uses_unknown(self):
        """Execute handles unparseable source_url gracefully."""
        ctx = PipelineContext(raw_input="test", input_type="text")
        ctx.result = _make_result(overall_score=55)
        ctx.content = _make_content(source_url="not-a-valid-url")
        effect = StatsCollectorSideEffect()
        with patch("urllib.parse.urlparse", side_effect=ValueError("bad url")):
            await effect.execute(ctx)
        assert "unknown" in effect._source_scores
