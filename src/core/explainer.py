"""Natural language explainer for junk-detector scoring results.

Generates concise Chinese explanations based on scoring dimensions and matched rules.
Quotes exact matched keywords/phrases with line number references.
"""

from __future__ import annotations

from typing import Optional

from src.core.rules import (
    RuleResult,
    _ADVERTORIAL_KEYWORDS,
    _ANXIETY_PHRASES,
    _SCAM_KEYWORDS,
)
from src.models.score import ScoreResult


def _find_keywords_with_lines(
    content: str, keywords: list[str], max_results: int = 4
) -> list[tuple[str, int]]:
    """Find which keywords appear in the content, with line numbers.

    Args:
        content: The original text content.
        keywords: List of keywords/phrases to search for.
        max_results: Maximum number of keyword matches to return.

    Returns:
        List of (keyword, line_number) tuples. Line numbers are 1-indexed.
    """
    import re

    lines = content.split("\n")
    found: list[tuple[str, int]] = []

    for kw in keywords:
        if len(found) >= max_results:
            break
        for line_idx, line in enumerate(lines):
            if kw in line or re.search(re.escape(kw), line):
                found.append((kw, line_idx + 1))
                break  # Only report first occurrence of each keyword

    return found


def _format_keyword_refs(matches: list[tuple[str, int]], multiline: bool) -> str:
    """Format keyword matches with optional line numbers.

    Args:
        matches: List of (keyword, line_number) tuples.
        multiline: Whether the original content has multiple lines.

    Returns:
        Formatted string like: "keyword1"(第N行)、"keyword2"(第M行)
    """
    parts = []
    for kw, line_num in matches:
        if multiline:
            parts.append(f'"{kw}"(第{line_num}行)')
        else:
            parts.append(f'"{kw}"')
    return "、".join(parts)


def _count_keyword_hits(rule_result: RuleResult, prefix: str) -> int:
    """Count matched rules that start with the given prefix."""
    return sum(1 for r in rule_result.matched_rules if r.startswith(prefix))


def _describe_scam(rule_result: RuleResult, content: Optional[str] = None) -> str:
    """Describe scam-related signals with keyword quoting."""
    scam_score = rule_result.dimension_overrides.get("scam_prob", 0)
    has_scam_keywords = "scam_keywords" in rule_result.matched_rules
    has_credibility = "credibility_unverifiable" in rule_result.matched_rules

    if has_scam_keywords and content:
        matches = _find_keywords_with_lines(content, _SCAM_KEYWORDS, max_results=4)
        if matches:
            multiline = "\n" in content
            refs = _format_keyword_refs(matches, multiline)
            return f"发现诈骗信号：{refs}"

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


def _describe_advertorial(rule_result: RuleResult, content: Optional[str] = None) -> str:
    """Describe advertorial-related signals with keyword quoting."""
    has_promo = "advertorial_promo" in rule_result.matched_rules
    platform_rules = [r for r in rule_result.matched_rules if r.startswith("platform_") and "patterns" in r]

    if has_promo and content:
        matches = _find_keywords_with_lines(content, _ADVERTORIAL_KEYWORDS, max_results=4)
        if matches:
            multiline = "\n" in content
            refs = _format_keyword_refs(matches, multiline)
            return f"疑似产品推荐：包含{refs}等商业推广词汇"

    parts = []
    if has_promo:
        parts.append("商业推广关键词")
    if platform_rules:
        parts.append("平台营销话术")

    if parts:
        return f"检测到{'、'.join(parts)}"
    return ""


def _describe_emotional(rule_result: RuleResult, content: Optional[str] = None) -> str:
    """Describe emotional manipulation signals with keyword quoting."""
    has_anxiety = "emotional_anxiety_phrases" in rule_result.matched_rules
    has_punctuation = "emotional_excessive_punctuation" in rule_result.matched_rules
    has_both = "emotional_anxiety_and_punctuation" in rule_result.matched_rules

    if (has_anxiety or has_both) and content:
        matches = _find_keywords_with_lines(content, _ANXIETY_PHRASES, max_results=4)
        if matches:
            multiline = "\n" in content
            refs = _format_keyword_refs(matches, multiline)
            return f"情绪操纵信号：{refs}"

    if has_both:
        return "存在焦虑话术和过度感叹号"
    if has_anxiety:
        return "存在情绪操纵话术"
    if has_punctuation:
        return "使用过多感叹号"
    return ""


def explain_result(
    score_result: ScoreResult,
    rule_result: RuleResult,
    content: Optional[str] = None,
) -> str:
    """Generate a one-sentence Chinese explanation based on scoring results.

    Args:
        score_result: The complete scoring result with overall_score and dimensions.
        rule_result: The rule engine result with matched_rules and dimension_overrides.
        content: Optional original text content for keyword quoting with line numbers.

    Returns:
        A Chinese string with emoji prefix explaining the scoring verdict.
    """
    overall = score_result.overall_score
    matched = rule_result.matched_rules

    # Collect signal descriptions
    signals: list[str] = []

    scam_desc = _describe_scam(rule_result, content)
    if scam_desc:
        signals.append(scam_desc)

    advertorial_desc = _describe_advertorial(rule_result, content)
    if advertorial_desc:
        signals.append(advertorial_desc)

    emotional_desc = _describe_emotional(rule_result, content)
    if emotional_desc:
        signals.append(emotional_desc)

    # Check for AI-generated signals
    if "ai_generated_signals" in matched:
        signals.append("疑似AI生成内容")

    # Honest uncertainty for borderline cases (score 40-55 with few signals)
    if 40 <= overall < 55 and len(signals) <= 1:
        return "\U0001f914 信号不够明确。建议结合其他信息源判断，不要完全依赖单一评分。"

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
            return "\u26a0\ufe0f 规则引擎未发现明显信号，得分偏低，建议人工复查或使用 LLM 深度分析。"

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
            return "\U0001f6a8 高风险内容。未匹配到已知模式，建议人工复查或启用 LLM 深度分析。"
