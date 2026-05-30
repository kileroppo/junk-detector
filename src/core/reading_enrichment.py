"""Attach API-facing reading_action and reference_value to ScoreResult."""

from __future__ import annotations

from typing import Any

from src.core.content_genre import GENRE_ROUNDUP, compute_reference_value_score
from src.models.score import ScoreResult


def enrich_score_result_fields(
    result: ScoreResult,
    *,
    content_text: str | None = None,
    title: str | None = None,
) -> ScoreResult:
    """Populate reading_action / reference_value without pulling in the web layer."""
    from src.web.result_display import (
        build_dimension_highlights,
        build_reading_action,
        build_reading_verdict,
        score_tier,
    )

    dims = result.dimensions.model_dump()
    genre = result.content_genre
    tier = score_tier(
        result.overall_score,
        content_genre=genre,
        dimensions=dims,
    )
    highlights = build_dimension_highlights(dims)
    verdict = build_reading_verdict(
        result.focus_guide,
        tier,
        result.overall_score,
        highlights,
        content_genre=genre,
    )
    action = build_reading_action(
        verdict,
        tier,
        content_genre=genre,
        dimensions=dims,
        overall_score=result.overall_score,
    )
    result.reading_action = action
    if genre == GENRE_ROUNDUP and content_text:
        result.reference_value = compute_reference_value_score(content_text)
    elif genre == GENRE_ROUNDUP:
        result.reference_value = None
    else:
        result.reference_value = None
    return result
