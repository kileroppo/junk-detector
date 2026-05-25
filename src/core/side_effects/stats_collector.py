"""Stats collector side effect — tracks scoring statistics for reporting."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

from src.core.pipeline import PipelineContext
from src.core.side_effects.base import SideEffect

logger = logging.getLogger("side_effects.stats")


class StatsCollectorSideEffect(SideEffect):
    """Collects aggregate scoring statistics.

    Tracks per-source and overall statistics:
    - Score distribution (avg, min, max, count)
    - Label frequency
    - Source quality rankings

    Stats are held in memory — query via .get_stats() method.
    """

    def __init__(self):
        self._source_scores: dict[str, list[float]] = defaultdict(list)
        self._label_counts: dict[str, int] = defaultdict(int)
        self._total_scored: int = 0
        self._total_score_sum: float = 0.0
        self._last_reset: datetime = datetime.now(timezone.utc)

    @property
    def name(self) -> str:
        return "stats_collector"

    async def should_trigger(self, ctx: PipelineContext) -> bool:
        """Always collect stats."""
        return ctx.result is not None

    async def execute(self, ctx: PipelineContext) -> None:
        """Record scoring statistics."""
        result = ctx.result
        content = ctx.content

        # Track overall
        self._total_scored += 1
        self._total_score_sum += result.overall_score

        # Track per-source
        source = "unknown"
        if content and content.source_url:
            from urllib.parse import urlparse

            try:
                source = urlparse(content.source_url).hostname or "unknown"
            except Exception:
                pass
        self._source_scores[source].append(result.overall_score)

        # Track labels
        for label in result.labels:
            self._label_counts[label] += 1

    def get_stats(self) -> dict:
        """Return current aggregate statistics."""
        avg_score = (self._total_score_sum / self._total_scored) if self._total_scored > 0 else 0

        # Source rankings (by average score, ascending = worst first)
        source_rankings = {}
        for source, scores in self._source_scores.items():
            source_rankings[source] = {
                "avg_score": sum(scores) / len(scores),
                "count": len(scores),
                "min_score": min(scores),
                "max_score": max(scores),
            }

        # Sort sources by avg score (worst first)
        sorted_sources = dict(sorted(source_rankings.items(), key=lambda x: x[1]["avg_score"]))

        return {
            "total_scored": self._total_scored,
            "avg_score": round(avg_score, 1),
            "label_frequency": dict(self._label_counts),
            "source_rankings": sorted_sources,
            "since": self._last_reset.isoformat(),
        }

    def reset(self) -> None:
        """Reset all statistics."""
        self._source_scores.clear()
        self._label_counts.clear()
        self._total_scored = 0
        self._total_score_sum = 0.0
        self._last_reset = datetime.now(timezone.utc)
