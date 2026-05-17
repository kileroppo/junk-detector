"""Main scoring orchestrator for junk-detector.

Coordinates the scoring pipeline: rules → LLM judge → compute overall → generate labels.
Implements tiered model strategy: rules → cheap model → expensive model for low-confidence.
"""

from __future__ import annotations

import logging

from src.core.llm_judge import judge
from src.core.rules import apply_rules
from src.models.score import DimensionScores, ScoreResult, ScoringConfig

logger = logging.getLogger(__name__)


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
        0. Pre-filter: reject obviously violating content (zero cost)
        1. Apply deterministic rules
        2. Check if rules cover ALL dimensions with high confidence → skip LLM
        3. Call LLM judge (primary model)
        4. If confidence < threshold → re-score with fallback model
        5. Apply high-confidence rule overrides on top of LLM results
        6. Record rule hits and model tier used
        7. Recalculate overall_score with configured weights
        8. Generate labels from thresholds

    Args:
        content_text: The text content to score.
        config: Optional scoring configuration. Uses defaults if None.

    Returns:
        Complete ScoreResult with dimensions, labels, and metadata.
    """
    if config is None:
        from src.core.config import load_config
        config = load_config()

    # 0. Pre-filter: reject obviously violating content before spending tokens
    from src.core.content_filter import check_content
    filter_result = check_content(content_text)
    if not filter_result.passed:
        logger.info(
            "Content rejected by pre-filter: %s — %s",
            filter_result.violation_type, filter_result.violation_details,
        )
        return ScoreResult(
            overall_score=0.0,
            dimensions=DimensionScores(
                originality=0,
                info_density=0,
                reasoning_quality=0,
                readability=0,
                timeliness=0,
                ai_generated_prob=0,
                emotional_manipulation=100,
                advertorial_prob=0,
                scam_prob=100,
            ),
            labels=[f"违规内容: {filter_result.violation_type}"],
            summary=f"内容被自动过滤: {filter_result.violation_details}",
            confidence=1.0,
            model_used="content_filter",
            cost=0.0,
            rule_hits=filter_result.matched_patterns,
        )

    # 1. Apply rules first
    rule_result = apply_rules(content_text)

    # 2. Check if rules alone can produce a full score (all 9 dimensions covered with high confidence)
    all_dimensions = [
        "originality", "info_density", "reasoning_quality", "readability", "timeliness",
        "ai_generated_prob", "emotional_manipulation", "advertorial_prob", "scam_prob",
    ]
    rules_covered = {
        dim for dim, conf in rule_result.confidence.items() if conf >= 0.9
    }

    if rules_covered >= set(all_dimensions):
        # Rules cover everything — skip LLM entirely (cost = 0)
        logger.info("All dimensions covered by rules, skipping LLM call")
        from src.models.score import DimensionScores as DS

        dims_dict = {dim: rule_result.dimension_overrides[dim] for dim in all_dimensions}
        dimensions = DS(**dims_dict)
        result = ScoreResult(
            overall_score=0,
            dimensions=dimensions,
            labels=[],
            summary="规则层直接判定",
            confidence=min(rule_result.confidence.values()),
            model_used="rules_only",
            cost=0.0,
            rule_hits=rule_result.matched_rules,
            dimension_sources={dim: "rule" for dim in all_dimensions},
        )
    else:
        # 3. Call LLM judge with primary model
        result = await judge(content_text, config)
        logger.info(
            "Primary model (%s) returned confidence=%.2f",
            config.primary_model, result.confidence,
        )

        # 4. If confidence below threshold → re-score with fallback model
        if result.confidence < config.confidence_threshold:
            logger.info(
                "Confidence %.2f < threshold %.2f, escalating to fallback model (%s)",
                result.confidence, config.confidence_threshold, config.fallback_model,
            )
            fallback_config = config.model_copy()
            fallback_config.primary_model = config.fallback_model
            fallback_result = await judge(content_text, fallback_config)

            # Use fallback result if it has higher confidence
            if fallback_result.confidence > result.confidence:
                result = fallback_result
                result.cost += result.cost  # accumulate cost from both calls
                logger.info(
                    "Fallback model confidence=%.2f, using fallback result",
                    fallback_result.confidence,
                )

        # 5. Apply rule overrides (high confidence rules override LLM dimensions)
        for dim, score_val in rule_result.dimension_overrides.items():
            conf = rule_result.confidence.get(dim, 0)
            if conf >= 0.9:
                setattr(result.dimensions, dim, score_val)
                result.dimension_sources[dim] = "rule"

    # 6. Record rule hits
    result.rule_hits = rule_result.matched_rules

    # 7. Recalculate overall_score with weights
    result.overall_score = _calculate_overall(result.dimensions, config)

    # 8. Generate labels from thresholds
    result.labels = _generate_labels(result.dimensions, config)

    return result
