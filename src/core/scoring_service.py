"""Scoring service - unified entry point for full scoring with report assembly."""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel

from src.models.score import ScoreResult, ScoringConfig

logger = logging.getLogger(__name__)


class ScoringReport(BaseModel):
    """Complete scoring report with all derived data."""

    result: ScoreResult
    rule_score: float
    llm_score: float
    divergence_warning: bool
    focus_guide: dict | None = None
    source_warning: dict | None = None
    rule_hits: list[str] = []
    dimension_sources: dict = {}
    rules_fired: bool = False
    score_divergence: float = 0.0


async def score_with_full_report(
    content_text: str,
    source_url: str | None = None,
    config: ScoringConfig | None = None,
) -> ScoringReport:
    """Score content and assemble a complete report.

    This consolidates the dual-score calculation, focus guide generation,
    source reputation check, and result assembly that was previously
    scattered across the router.

    Args:
        content_text: The text content to score.
        source_url: Optional URL source of the content.
        config: Optional scoring configuration override.

    Returns:
        A ScoringReport with full scoring results and derived data.
    """
    from src.core.rules import apply_rules
    from src.core.scorer import _calculate_overall, score
    from src.models.score import DimensionScores

    # Score with LLM
    result = await score(content_text, config=config, source_url=source_url)

    # Compute rule-only score for dual comparison
    rule_result = apply_rules(content_text)
    rule_dims_dict: dict[str, float] = {}
    for dim in ["originality", "info_density", "reasoning_quality", "readability", "timeliness"]:
        rule_dims_dict[dim] = rule_result.dimension_overrides.get(dim, 50.0)
    for dim in ["ai_generated_prob", "emotional_manipulation", "advertorial_prob", "scam_prob"]:
        rule_dims_dict[dim] = rule_result.dimension_overrides.get(dim, 0.0)

    rule_dimensions = DimensionScores(**rule_dims_dict)

    if config is None:
        try:
            from src.core.config import load_config

            config = load_config()
        except Exception:
            config = None

    if config:
        rule_only_score = _calculate_overall(rule_dimensions, config)
    else:
        rule_only_score = 50.0

    llm_score = result.overall_score
    score_divergence = abs(rule_only_score - llm_score)
    rules_fired = bool(rule_result.matched_rules)
    divergence_warning = score_divergence > 20 and rules_fired

    # Generate focus guide if content is likely AI-generated or low quality
    focus_guide = None
    if result.overall_score < 70 or result.dimensions.ai_generated_prob > 30:
        try:
            from src.core.focus_guide import generate_focus_guide

            guide = generate_focus_guide(content_text, result)
            if guide:
                focus_guide = guide.model_dump()
        except Exception:
            logger.debug("Focus guide generation failed")

    # Source reputation check
    source_warning = None
    if source_url:
        from urllib.parse import urlparse

        from src.core.source_reputation import check_auto_blacklist, is_blacklisted

        try:
            parsed = urlparse(source_url)
            domain = parsed.netloc or ""
            if domain.startswith("www."):
                domain = domain[4:]
            if domain:
                if is_blacklisted(domain):
                    source_warning = {"level": "blacklisted", "message": "来源已列入黑名单"}
                elif check_auto_blacklist(domain):
                    source_warning = {"level": "low_reputation", "message": "该来源历史评分较低"}
        except Exception:
            pass

    return ScoringReport(
        result=result,
        rule_score=rule_only_score,
        llm_score=llm_score,
        divergence_warning=divergence_warning,
        focus_guide=focus_guide,
        source_warning=source_warning,
        rule_hits=result.rule_hits,
        dimension_sources=result.dimension_sources or {},
        rules_fired=rules_fired,
        score_divergence=score_divergence,
    )
