"""Natural language explainer for junk-detector scoring results.

Generates concise Chinese explanations based on scoring dimensions and matched rules.
"""

from __future__ import annotations

from src.core.rules import RuleResult
from src.models.score import ScoreResult


def _count_keyword_hits(rule_result: RuleResult, prefix: str) -> int:
    """Count matched rules that start with the given prefix."""
    return sum(1 for r in rule_result.matched_rules if r.startswith(prefix))


def _describe_scam(rule_result: RuleResult) -> str:
    """Describe scam-related signals."""
    scam_score = rule_result.dimension_overrides.get("scam_prob", 0)
    has_scam_keywords = "scam_keywords" in rule_result.matched_rules
    has_credibility = "credibility_unverifiable" in rule_result.matched_rules

    parts = []
    if has_scam_keywords:
        parts.append("诈骗关键词")
    if has_credibility:
        parts.append("不可验证声明")

    if parts:
        return f"发现{len(parts)}类风险信号（{'、'.join(parts)}）"
    if scam_score > 0:
        return "存在诈骗风险特征"
    return ""


def _describe_advertorial(rule_result: RuleResult) -> str:
    """Describe advertorial-related signals."""
    has_promo = "advertorial_promo" in rule_result.matched_rules
    platform_rules = [r for r in rule_result.matched_rules if r.startswith("platform_") and "patterns" in r]

    parts = []
    if has_promo:
        parts.append("商业推广关键词")
    if platform_rules:
        parts.append("平台营销话术")

    if parts:
        return f"检测到{'、'.join(parts)}"
    return ""


def _describe_emotional(rule_result: RuleResult) -> str:
    """Describe emotional manipulation signals."""
    has_anxiety = "emotional_anxiety_phrases" in rule_result.matched_rules
    has_punctuation = "emotional_excessive_punctuation" in rule_result.matched_rules
    has_both = "emotional_anxiety_and_punctuation" in rule_result.matched_rules

    if has_both:
        return "存在焦虑话术和过度感叹号"
    if has_anxiety:
        return "存在情绪操纵话术"
    if has_punctuation:
        return "使用过多感叹号"
    return ""


def explain_result(score_result: ScoreResult, rule_result: RuleResult) -> str:
    """Generate a one-sentence Chinese explanation based on scoring results.

    Args:
        score_result: The complete scoring result with overall_score and dimensions.
        rule_result: The rule engine result with matched_rules and dimension_overrides.

    Returns:
        A Chinese string with emoji prefix explaining the scoring verdict.
    """
    overall = score_result.overall_score
    matched = rule_result.matched_rules

    # Collect signal descriptions
    signals: list[str] = []

    scam_desc = _describe_scam(rule_result)
    if scam_desc:
        signals.append(scam_desc)

    advertorial_desc = _describe_advertorial(rule_result)
    if advertorial_desc:
        signals.append(advertorial_desc)

    emotional_desc = _describe_emotional(rule_result)
    if emotional_desc:
        signals.append(emotional_desc)

    # Check for AI-generated signals
    if "ai_generated_signals" in matched:
        signals.append("疑似AI生成内容")

    # Count total matched rules (excluding combos for display)
    non_combo_count = len([r for r in matched if not r.startswith("combo_")])

    # Generate explanation based on score tier
    if overall >= 70:
        # Good content
        if signals:
            detail = f"，但有轻微信号：{'；'.join(signals)}"
        else:
            detail = "，论证清晰，信息密度较高"
        return f"\u2705 内容质量正常{detail}。"

    elif overall >= 40:
        # Borderline content
        if signals:
            detail = "；".join(signals)
            return f"\u26a0\ufe0f 内容存在风险信号。{detail}，建议人工复核。"
        else:
            return "\u26a0\ufe0f 内容质量一般，未发现明显风险但得分偏低。"

    else:
        # Junk / high-risk content
        if signals:
            detail = "；".join(signals)
            rule_count = non_combo_count
            if rule_count > 0:
                return f"\U0001f6a8 高风险内容。命中 {rule_count} 条规则：{detail}。"
            else:
                return f"\U0001f6a8 高风险内容。{detail}。"
        else:
            return "\U0001f6a8 高风险内容。综合评分极低，存在多项质量问题。"
