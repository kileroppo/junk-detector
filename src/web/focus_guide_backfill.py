"""Backfill focus_guide on result pages when older scores omitted it."""

from __future__ import annotations

from typing import Any


def ensure_record_focus_guide(record: dict[str, Any]) -> dict[str, Any]:
    """Generate focus guide at view-time if missing but content_text is available."""
    if record.get("focus_guide"):
        return record
    content_text = record.get("content_text") or ""
    if len(content_text.strip()) < 50:
        return record

    from src.core.focus_guide import generate_focus_guide
    from src.models.score import DimensionScores, ScoreResult

    dims = record.get("dimensions") or {}
    try:
        dimensions = DimensionScores(**dims)
    except Exception:
        return record

    score = ScoreResult(
        overall_score=float(record.get("overall_score", 50)),
        dimensions=dimensions,
        labels=record.get("labels") or [],
        summary=record.get("summary") or "",
        content_genre=record.get("content_genre"),
    )
    guide = generate_focus_guide(content_text, score)
    if guide is None:
        return record

    updated = dict(record)
    updated["focus_guide"] = guide.model_dump()
    return updated
