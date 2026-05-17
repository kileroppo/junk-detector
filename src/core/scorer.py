"""Main scoring orchestrator for junk-detector.

Coordinates the scoring pipeline: rules → LLM judge → compute overall → generate labels.
"""

from __future__ import annotations

from src.core.llm_judge import judge
from src.core.rules import apply_rules
from src.models.score import DimensionScores, ScoreResult, ScoringConfig


def _calculate_overall(dimensions: DimensionScores, config: ScoringConfig) -> float:
    """Calculate weighted overall score from dimension scores.

    Positive dimensions contribute directly, negative dimensions contribute
    inversely (higher negative score → lower overall).

    Returns:
        Overall score clamped to 0-100, rounded to 1 decimal.
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for dim, weight in config.weights.items():
        score = getattr(dimensions, dim)
        if weight > 0:
            weighted_sum += score * weight
            total_weight += weight * 100
        else:
            # Negative dimensions: higher score → lower overall
            weighted_sum += (100 - score) * abs(weight)
            total_weight += abs(weight) * 100

    overall = (weighted_sum / total_weight) * 100 if total_weight > 0 else 50.0
    return round(max(0.0, min(100.0, overall)), 1)


def _generate_labels(dimensions: DimensionScores, config: ScoringConfig) -> list[str]:
    """Generate labels based on dimension scores and configured thresholds.

    Maps dimension names to label thresholds defined in config.label_thresholds.

    Returns:
        List of label strings that were triggered.
    """
    labels: list[str] = []

    # Map label names to the dimension they check
    label_to_dimension: dict[str, str] = {
        "可能AI生成": "ai_generated_prob",
        "情绪操纵": "emotional_manipulation",
        "疑似软文": "advertorial_prob",
        "疑似骗局": "scam_prob",
        "高质量原创": "originality",
        "信息密度高": "info_density",
    }

    for label, dimension in label_to_dimension.items():
        threshold = config.label_thresholds.get(label)
        if threshold is None:
            continue
        score = getattr(dimensions, dimension, None)
        if score is not None and score >= threshold:
            labels.append(label)

    return labels


async def score(content_text: str, config: ScoringConfig | None = None) -> ScoreResult:
    """Main scoring orchestrator.

    Pipeline:
        1. Apply deterministic rules
        2. Call LLM judge for full dimension scoring
        3. Apply high-confidence rule overrides on top of LLM results
        4. Record rule hits
        5. Recalculate overall_score with configured weights
        6. Generate labels from thresholds

    Args:
        content_text: The text content to score.
        config: Optional scoring configuration. Uses defaults if None.

    Returns:
        Complete ScoreResult with dimensions, labels, and metadata.
    """
    if config is None:
        config = ScoringConfig()

    # 1. Apply rules first
    rule_result = apply_rules(content_text)

    # 2. Call LLM judge
    result = await judge(content_text, config)

    # 3. Apply rule overrides (high confidence rules override LLM dimensions)
    for dim, score_val in rule_result.dimension_overrides.items():
        conf = rule_result.confidence.get(dim, 0)
        if conf >= 0.9:
            setattr(result.dimensions, dim, score_val)
            result.dimension_sources[dim] = "rule"

    # 4. Record rule hits
    result.rule_hits = rule_result.matched_rules

    # 5. Recalculate overall_score with weights
    result.overall_score = _calculate_overall(result.dimensions, config)

    # 6. Generate labels from thresholds
    result.labels = _generate_labels(result.dimensions, config)

    return result
