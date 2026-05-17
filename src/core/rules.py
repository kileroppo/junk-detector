"""Deterministic rules engine for junk-detector.

Fast, regex/keyword-based pattern matching to detect obvious content quality
signals without needing LLM calls. Rules fire independently and produce
dimension score overrides with associated confidence levels.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field


class RuleResult(BaseModel):
    """Result of applying all rules against a piece of content."""

    matched_rules: list[str] = Field(
        default_factory=list, description="Names of rules that fired"
    )
    dimension_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Dimension name → score to override (e.g. {'scam_prob': 95})",
    )
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Confidence per matched dimension (0-1)",
    )


# ---------------------------------------------------------------------------
# Scam / 韭菜收割 rules
# ---------------------------------------------------------------------------

_SCAM_KEYWORDS: list[str] = [
    "日入过万",
    "躺赚",
    "财富自由",
    "限时免费",
    "私聊领取",
    "月入百万",
    "被动收入",
    "零成本",
    "稳赚不赔",
    "加微信",
    "免费领取",
    "名额有限",
    "最后一天",
]


def _check_scam_keywords(content: str) -> Optional[tuple[float, float]]:
    """Check for scam/韭菜收割 keyword density.

    Returns (score, confidence) or None if not triggered.
    """
    hit_count = sum(1 for kw in _SCAM_KEYWORDS if kw in content)

    if hit_count >= 3:
        return (95.0, 0.95)
    elif hit_count >= 1:
        return (75.0, 0.8)
    return None


# ---------------------------------------------------------------------------
# Emotional manipulation rules
# ---------------------------------------------------------------------------

_ANXIETY_PHRASES: list[str] = [
    "再不.*就晚了",
    "99%的人不知道",
    "震惊",
    "必看",
    "紧急",
]

# Pre-compile anxiety patterns for performance
_ANXIETY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(phrase) for phrase in _ANXIETY_PHRASES
]


def _check_excessive_punctuation(content: str) -> bool:
    """Check if exclamation marks exceed 5 per 1000 characters."""
    exclamation_count = content.count("!") + content.count("！")
    text_length = max(len(content), 1)  # avoid division by zero
    rate_per_1000 = (exclamation_count / text_length) * 1000
    return rate_per_1000 > 5


def _check_anxiety_phrases(content: str) -> int:
    """Count how many anxiety phrase patterns match."""
    return sum(1 for pattern in _ANXIETY_PATTERNS if pattern.search(content))


def _check_emotional_manipulation(content: str) -> Optional[tuple[float, float]]:
    """Check for emotional manipulation signals.

    Returns (score, confidence) or None if not triggered.
    """
    has_excessive_punctuation = _check_excessive_punctuation(content)
    anxiety_count = _check_anxiety_phrases(content)

    # Combined signal: anxiety phrases + excessive punctuation
    if anxiety_count > 0 and has_excessive_punctuation:
        return (85.0, 0.9)

    # Excessive punctuation alone
    if has_excessive_punctuation:
        return (70.0, 0.75)

    # Anxiety phrases alone (multiple)
    if anxiety_count >= 2:
        return (70.0, 0.75)

    return None


# ---------------------------------------------------------------------------
# Advertorial rules
# ---------------------------------------------------------------------------

_ADVERTORIAL_KEYWORDS: list[str] = [
    "推荐码",
    "优惠券",
    "折扣码",
    "点击链接",
    "复制口令",
]

_HTTP_LINK_PATTERN: re.Pattern[str] = re.compile(r"https?://\S+")


def _check_advertorial(content: str) -> Optional[tuple[float, float]]:
    """Check for advertorial/commercial promotion signals.

    Returns (score, confidence) or None if not triggered.
    """
    keyword_hits = sum(1 for kw in _ADVERTORIAL_KEYWORDS if kw in content)
    link_count = len(_HTTP_LINK_PATTERN.findall(content))

    # High link density (3+ links) combined with promo keywords
    has_high_link_density = link_count >= 3

    if keyword_hits >= 1 and has_high_link_density:
        return (80.0, 0.85)

    # Promo keywords alone (2+)
    if keyword_hits >= 2:
        return (80.0, 0.85)

    # Single promo keyword
    if keyword_hits == 1:
        return (60.0, 0.7)

    # High link density alone
    if has_high_link_density:
        return (55.0, 0.6)

    return None


# ---------------------------------------------------------------------------
# AI-generated content rules
# ---------------------------------------------------------------------------

_AI_HEDGING_PHRASES: list[str] = [
    "需要注意的是",
    "值得一提的是",
    "总的来说",
    "综上所述",
]


def _calculate_lexical_diversity(content: str) -> float:
    """Calculate lexical diversity as unique chars / total chars.

    For Chinese text, we use character-level diversity since word
    segmentation would be too expensive for a rules engine.
    Returns value between 0 and 1 (lower = more repetitive).
    """
    if not content:
        return 1.0
    # Filter out whitespace and punctuation for diversity calculation
    chars = [c for c in content if c.strip() and not c in "，。！？、；：""''（）【】《》…—·"]
    if not chars:
        return 1.0
    unique_chars = set(chars)
    return len(unique_chars) / len(chars)


def _check_ai_generated(content: str) -> Optional[tuple[float, float]]:
    """Check for AI-generated content signals.

    Returns (score, confidence) or None if not triggered.
    Lower confidence because this needs LLM confirmation.
    """
    # Count hedging phrases
    hedging_count = sum(content.count(phrase) for phrase in _AI_HEDGING_PHRASES)

    # Check lexical diversity (very low diversity suggests AI generation)
    diversity = _calculate_lexical_diversity(content)
    low_diversity = diversity < 0.4 and len(content) > 200

    if hedging_count >= 3:
        return (65.0, 0.6)

    if low_diversity and hedging_count >= 1:
        return (65.0, 0.6)

    if low_diversity:
        return (55.0, 0.5)

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def apply_rules(content: str) -> RuleResult:
    """Apply all deterministic rules against content.

    Runs fast keyword/regex matching across all rule categories and returns
    any dimension overrides with confidence scores.

    Args:
        content: The text content to analyze.

    Returns:
        RuleResult with matched rules, dimension overrides, and confidence.
    """
    result = RuleResult()

    if not content:
        return result

    # --- Scam rules ---
    scam_result = _check_scam_keywords(content)
    if scam_result is not None:
        score, conf = scam_result
        result.matched_rules.append("scam_keywords")
        result.dimension_overrides["scam_prob"] = score
        result.confidence["scam_prob"] = conf

    # --- Emotional manipulation rules ---
    emotional_result = _check_emotional_manipulation(content)
    if emotional_result is not None:
        score, conf = emotional_result
        rule_name = "emotional_manipulation"
        if _check_excessive_punctuation(content) and _check_anxiety_phrases(content) > 0:
            rule_name = "emotional_anxiety_and_punctuation"
        elif _check_excessive_punctuation(content):
            rule_name = "emotional_excessive_punctuation"
        else:
            rule_name = "emotional_anxiety_phrases"
        result.matched_rules.append(rule_name)
        result.dimension_overrides["emotional_manipulation"] = score
        result.confidence["emotional_manipulation"] = conf

    # --- Advertorial rules ---
    advertorial_result = _check_advertorial(content)
    if advertorial_result is not None:
        score, conf = advertorial_result
        result.matched_rules.append("advertorial_promo")
        result.dimension_overrides["advertorial_prob"] = score
        result.confidence["advertorial_prob"] = conf

    # --- AI-generated rules ---
    ai_result = _check_ai_generated(content)
    if ai_result is not None:
        score, conf = ai_result
        result.matched_rules.append("ai_generated_signals")
        result.dimension_overrides["ai_generated_prob"] = score
        result.confidence["ai_generated_prob"] = conf

    return result
