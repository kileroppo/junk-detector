"""Main scoring orchestrator for junk-detector.

Coordinates the scoring pipeline: rules → LLM judge → compute overall → generate labels.
Implements tiered model strategy: rules → cheap model → expensive model for low-confidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from src.core.content_optimizer import smart_truncate
from src.core.llm_judge import judge
from src.core.platform_profiles import (
    apply_platform_weights,
    check_platform_extra_rules,
    detect_platform,
)
from src.core.rules import apply_rules, should_skip_llm
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


async def score(
    content_text: str,
    config: ScoringConfig | None = None,
    source_url: str | None = None,
    language: str = "zh",
) -> ScoreResult:
    """Main scoring orchestrator.

    Pipeline:
        0. Detect platform from source_url and apply weight overrides
        1. Apply deterministic rules (including platform-specific extra rules)
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
        source_url: Optional source URL for platform-specific scoring adjustments.
        language: Language code for prompt template ("zh" or "en"). Defaults to "zh".

    Returns:
        Complete ScoreResult with dimensions, labels, and metadata.
    """
    if config is None:
        from src.core.config import load_config

        config = load_config()

    # Pre-filter: reject obviously violating content before spending tokens
    from src.core.content_filter import check_content

    filter_result = check_content(content_text)
    if not filter_result.passed:
        logger.info(
            "Content rejected by pre-filter: %s — %s",
            filter_result.violation_type,
            filter_result.violation_details,
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

    # Cache check: return cached result if scored within 7 days
    content_hash = hashlib.sha256(content_text.encode()).hexdigest()
    try:
        from src.storage.db import query_by_content_hash

        cached = query_by_content_hash(content_hash)
        if cached:
            scored_at_str = cached.get("scored_at", "")
            if scored_at_str:
                scored_at_dt = datetime.fromisoformat(scored_at_str)
                if scored_at_dt.tzinfo is None:
                    scored_at_dt = scored_at_dt.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if now - scored_at_dt < timedelta(days=7):
                    logger.info("Returning cached result (content_hash=%s)", content_hash[:12])
                    return ScoreResult(
                        overall_score=cached["overall_score"],
                        dimensions=DimensionScores(**cached["dimensions"]),
                        labels=cached.get("labels", []),
                        summary=cached.get("summary", ""),
                        confidence=cached.get("confidence", 1.0),
                        model_used="cache",
                        cost=0.0,
                        rule_hits=cached.get("rule_hits", []),
                    )
    except Exception as e:
        logger.debug("Cache lookup failed: %s", e)

    # FastClassifier pre-screen — skip LLM for high-confidence predictions
    try:
        from src.core.fast_classifier import classify_fast

        classifier_result = classify_fast(content_text)
        if classifier_result.should_skip_llm:
            logger.info(
                "FastClassifier: skipping LLM (category=%s, confidence=%.2f, score=%s)",
                classifier_result.category,
                classifier_result.confidence,
                classifier_result.predicted_score,
            )
            # TODO: convert classifier_result to full ScoreResult in future
            # For now, just log and continue to LLM (until we have enough training data)
    except Exception as e:
        logger.debug(f"FastClassifier unavailable: {e}")

    # 0. Apply platform-specific weight overrides
    platform = "default"
    if source_url:
        platform = detect_platform(source_url)
        if platform != "default":
            logger.info("Detected platform: %s (from %s)", platform, source_url)
            config = config.model_copy(deep=True)
            config.weights = apply_platform_weights(config.weights, platform)

    # 1. Apply rules first
    rule_result = apply_rules(content_text)

    # 1.5. Check platform-specific extra rules and boost signals if matched
    platform_rule_hits = check_platform_extra_rules(content_text, platform)
    if platform_rule_hits:
        logger.info("Platform extra rules matched: %s", platform_rule_hits)
        rule_result.matched_rules.extend([f"platform_{platform}:{kw}" for kw in platform_rule_hits])
        # Boost advertorial_prob if platform extra rules fire (self-promotion signals)
        current_advertorial = rule_result.dimension_overrides.get("advertorial_prob", 0)
        boost = min(len(platform_rule_hits) * 15, 40)  # +15 per keyword, max +40
        new_advertorial = min(current_advertorial + boost, 100.0)
        if new_advertorial > current_advertorial:
            rule_result.dimension_overrides["advertorial_prob"] = new_advertorial
            # Set confidence if not already set or lower
            existing_conf = rule_result.confidence.get("advertorial_prob", 0)
            rule_result.confidence["advertorial_prob"] = max(existing_conf, 0.7)

    # 1.6. Smart rules skip: check if rules are confident enough to skip LLM entirely
    skip_llm, skip_reason = should_skip_llm(rule_result, content_text)
    if skip_llm:
        logger.info("Smart rules skip triggered: reason=%s", skip_reason)
        # Construct ScoreResult from rule overrides, filling missing dims with defaults
        _positive_default = 50.0
        _negative_default = 0.0
        positive_dims_list = [
            "originality",
            "info_density",
            "reasoning_quality",
            "readability",
            "timeliness",
        ]
        negative_dims_list = [
            "ai_generated_prob",
            "emotional_manipulation",
            "advertorial_prob",
            "scam_prob",
        ]

        dims_dict: dict[str, float] = {}
        for dim in positive_dims_list:
            dims_dict[dim] = rule_result.dimension_overrides.get(dim, _positive_default)
        for dim in negative_dims_list:
            dims_dict[dim] = rule_result.dimension_overrides.get(dim, _negative_default)

        dimensions = DimensionScores(**dims_dict)
        result = ScoreResult(
            overall_score=0,
            dimensions=dimensions,
            labels=[],
            summary="规则高置信度判定，跳过LLM",
            confidence=min(rule_result.confidence.values()) if rule_result.confidence else 0.85,
            model_used="rules_skip",
            cost=0.0,
            rule_hits=rule_result.matched_rules,
            dimension_sources={dim: "rule" for dim in rule_result.dimension_overrides},
        )

        # 7. Recalculate overall_score with weights
        result.overall_score = _calculate_overall(result.dimensions, config)

        # 8. Generate labels from thresholds
        result.labels = _generate_labels(result.dimensions, config)

        # Track stats
        try:
            from src.storage.db import increment_rules_only

            increment_rules_only()
        except Exception as e:
            logger.debug("Failed to increment rules_only stats: %s", e)

        return result

    # 2. Check if rules alone can produce a full score (all 9 dimensions covered with high confidence)
    all_dimensions = [
        "originality",
        "info_density",
        "reasoning_quality",
        "readability",
        "timeliness",
        "ai_generated_prob",
        "emotional_manipulation",
        "advertorial_prob",
        "scam_prob",
    ]
    rules_covered = {dim for dim, conf in rule_result.confidence.items() if conf >= 0.9}

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

        # Track stats
        try:
            from src.storage.db import increment_rules_only

            increment_rules_only()
        except Exception as e:
            logger.debug("Failed to increment rules_only stats: %s", e)
    else:
        # 3. Call LLM judge with primary model
        # Determine which dimensions still need LLM evaluation
        required_dimensions = [dim for dim in all_dimensions if dim not in rules_covered]

        # Apply smart truncation to content before sending to LLM
        truncated_content = smart_truncate(content_text)

        result = await judge(
            truncated_content, config, language=language, required_dimensions=required_dimensions
        )
        logger.info(
            "Primary model (%s) returned confidence=%.2f",
            config.primary_model,
            result.confidence,
        )

        # 4. If confidence below threshold → re-score with fallback model
        if result.confidence < config.confidence_threshold:
            logger.info(
                "Confidence %.2f < threshold %.2f, escalating to fallback model (%s)",
                result.confidence,
                config.confidence_threshold,
                config.fallback_model,
            )
            fallback_config = config.model_copy(deep=True)
            fallback_config.primary_model = config.fallback_model
            fallback_result = await judge(
                truncated_content,
                fallback_config,
                language=language,
                required_dimensions=required_dimensions,
            )

            # Use fallback result if it has higher confidence
            if fallback_result.confidence > result.confidence:
                primary_cost = result.cost
                result = fallback_result
                result.cost = primary_cost + fallback_result.cost
                logger.info(
                    "Fallback model confidence=%.2f, using fallback result",
                    fallback_result.confidence,
                )

        # 4.5. Output validation: detect suspicious LLM outputs
        dims = result.dimensions
        positive_dims = [
            dims.originality,
            dims.info_density,
            dims.reasoning_quality,
            dims.readability,
            dims.timeliness,
        ]
        negative_dims = [
            dims.ai_generated_prob,
            dims.emotional_manipulation,
            dims.advertorial_prob,
            dims.scam_prob,
        ]
        all_dims = positive_dims + negative_dims

        suspicious = False
        if all(d == 100 for d in all_dims):
            suspicious = True
        elif all(d == 0 for d in all_dims):
            suspicious = True
        elif all(d >= 98 for d in positive_dims) and all(d <= 2 for d in negative_dims):
            suspicious = True
        elif all(d <= 2 for d in positive_dims) and all(d >= 98 for d in negative_dims):
            suspicious = True

        if suspicious:
            logger.warning(
                "Suspicious LLM output detected (possible prompt injection): dims=%s",
                all_dims,
            )
            result = ScoreResult(
                overall_score=50.0,
                dimensions=DimensionScores(
                    originality=50,
                    info_density=50,
                    reasoning_quality=50,
                    readability=50,
                    timeliness=50,
                    ai_generated_prob=50,
                    emotional_manipulation=50,
                    advertorial_prob=50,
                    scam_prob=50,
                ),
                labels=[],
                summary="LLM输出异常，可能存在prompt注入",
                confidence=0.1,
                model_used="validation_rejected",
                cost=result.cost,
                rule_hits=[],
            )
            return result

        # 4.6. Detect injection indicators in response text
        injection_phrases = [
            # English
            "ignore previous",
            "ignore all",
            "override instructions",
            "disregard above",
            "ignore above",
            "new instructions",
            "system prompt",
            "forget everything",
            # Chinese (中文注入检测)
            "忽略上述",
            "忽略以上",
            "忽略之前",
            "忽略所有",
            "无视上述",
            "无视以上",
            "新的指令",
            "重新定义",
            "系统提示",
            "覆盖指令",
        ]
        response_text = (result.summary or "").lower() + " " + " ".join(result.labels).lower()
        if any(phrase in response_text for phrase in injection_phrases):
            logger.warning(
                "Injection indicator detected in LLM response: summary=%s, labels=%s",
                result.summary,
                result.labels,
            )
            result = ScoreResult(
                overall_score=50.0,
                dimensions=DimensionScores(
                    originality=50,
                    info_density=50,
                    reasoning_quality=50,
                    readability=50,
                    timeliness=50,
                    ai_generated_prob=50,
                    emotional_manipulation=50,
                    advertorial_prob=50,
                    scam_prob=50,
                ),
                labels=[],
                summary="LLM输出异常，可能存在prompt注入",
                confidence=0.1,
                model_used="validation_rejected",
                cost=result.cost,
                rule_hits=[],
            )
            return result

        # 5. Apply rule overrides (high confidence rules override LLM dimensions)
        for dim, score_val in rule_result.dimension_overrides.items():
            conf = rule_result.confidence.get(dim, 0)
            if conf >= 0.9:
                setattr(result.dimensions, dim, score_val)
                result.dimension_sources[dim] = "rule"

        # Track stats
        try:
            from src.storage.db import increment_llm_count

            increment_llm_count()
        except Exception as e:
            logger.debug("Failed to increment llm_count stats: %s", e)

    # 6. Record rule hits
    result.rule_hits = rule_result.matched_rules

    # 7. Recalculate overall_score with weights
    result.overall_score = _calculate_overall(result.dimensions, config)

    # 8. Generate labels from thresholds
    result.labels = _generate_labels(result.dimensions, config)

    # Track ROI: compare rules-only score with final LLM score (after step 7)
    if not skip_llm and not (rules_covered >= set(all_dimensions)):
        try:
            from src.core.token_roi import compute_roi, save_roi_record

            if result.tokens_used > 0:
                # Compute a rules-only score from dimension_overrides
                _positive_default = 50.0
                _negative_default = 0.0
                positive_dims_for_roi = [
                    "originality",
                    "info_density",
                    "reasoning_quality",
                    "readability",
                    "timeliness",
                ]
                negative_dims_for_roi = [
                    "ai_generated_prob",
                    "emotional_manipulation",
                    "advertorial_prob",
                    "scam_prob",
                ]
                roi_dims_dict: dict[str, float] = {}
                for dim in positive_dims_for_roi:
                    roi_dims_dict[dim] = rule_result.dimension_overrides.get(
                        dim, _positive_default
                    )
                for dim in negative_dims_for_roi:
                    roi_dims_dict[dim] = rule_result.dimension_overrides.get(
                        dim, _negative_default
                    )
                rules_only_dims = DimensionScores(**roi_dims_dict)
                rules_only_score = _calculate_overall(rules_only_dims, config)

                roi = compute_roi(rules_only_score, result.overall_score, result.tokens_used)
                save_roi_record(
                    content_hash=content_hash,
                    tokens_used=result.tokens_used,
                    rules_score=rules_only_score,
                    llm_score=result.overall_score,
                    roi=roi,
                )
        except Exception as e:
            logger.debug("Failed to track ROI: %s", e)

    return result
