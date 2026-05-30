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


def _platform_context(platform: str, matched_rules: list[str]) -> str:
    """Generate platform-specific context explanation.

    Args:
        platform: Detected platform name (e.g. 'xiaohongshu', 'wechat', 'zhihu').
        matched_rules: List of matched rule names.

    Returns:
        A Chinese string with platform-specific context, or empty string.
    """
    has_advertorial = any(
        "advertorial" in r or "promo" in r or "patterns" in r for r in matched_rules
    )
    has_scam = any("scam" in r for r in matched_rules)

    if platform == "xiaohongshu" and has_advertorial:
        return '\u5728\u5c0f\u7ea2\u4e66\u4e0a\uff0c"\u59d0\u59b9\u4eec"\u5f00\u5934 + \u4ea7\u54c1\u94fe\u63a5\u901a\u5e38\u8868\u793a\u8f6f\u6587\u5408\u4f5c\u3002'

    if platform == "wechat" and has_scam:
        return "\u516c\u4f17\u53f7\u6587\u7ae0\u4e2d\u51fa\u73b0\u7684\u6295\u8d44\u63a8\u8350\u9700\u8981\u683c\u5916\u8c28\u614e\u3002"

    if platform == "zhihu" and matched_rules:
        return '\u77e5\u4e4e\u4e0a\u7684"\u7ecf\u9a8c\u5206\u4eab"\u6709\u65f6\u4e5f\u662f\u4f2a\u88c5\u7684\u5546\u4e1a\u63a8\u5e7f\u3002'

    return ""


def _confidence_language(confidence: float, signal_count: int) -> str:
    """Express confidence level in natural Chinese language.

    Args:
        confidence: Confidence score between 0 and 1.
        signal_count: Number of signals/rules that matched.

    Returns:
        A Chinese string describing the confidence level naturally.
    """
    if confidence > 0.8:
        return f"\u6211\u6bd4\u8f83\u786e\u5b9a\u8fd9\u662f\u95ee\u9898\u5185\u5bb9\uff08\u57fa\u4e8e {signal_count} \u4e2a\u660e\u786e\u4fe1\u53f7\uff09"

    if confidence >= 0.5:
        return "\u6709\u4e00\u4e9b\u53ef\u7591\u8ff9\u8c61\uff0c\u4f46\u4e0d\u5b8c\u5168\u786e\u5b9a"

    return f"\u4e0d\u592a\u786e\u5b9a\uff0c\u53ea\u53d1\u73b0\u4e86 {signal_count} \u4e2a\u8f7b\u5fae\u53ef\u7591\u70b9\uff0c\u5efa\u8bae\u81ea\u884c\u5224\u65ad"


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


def determine_severity(
    score_result: ScoreResult, rule_result: Optional[RuleResult] = None
) -> str:
    """Map scoring dimensions to a severity level.

    Args:
        score_result: The scoring result with dimension scores.
        rule_result: Optional rule engine result with dimension_overrides.

    Returns:
        One of: 'danger', 'warning', 'info', 'safe'.
    """
    # Use rule_result dimension_overrides if available, otherwise use score_result dimensions
    if rule_result is not None:
        scam_prob = rule_result.dimension_overrides.get("scam_prob", 0)
        advertorial_prob = rule_result.dimension_overrides.get("advertorial_prob", 0)
        emotional_manipulation = rule_result.dimension_overrides.get(
            "emotional_manipulation", 0
        )
    else:
        scam_prob = getattr(score_result.dimensions, "scam_prob", 0)
        advertorial_prob = getattr(score_result.dimensions, "advertorial_prob", 0)
        emotional_manipulation = getattr(
            score_result.dimensions, "emotional_manipulation", 0
        )

    if scam_prob >= 60:
        return "danger"
    elif advertorial_prob >= 60 or emotional_manipulation >= 60:
        return "warning"
    elif scam_prob > 0 or advertorial_prob > 0 or emotional_manipulation > 0:
        return "info"
    else:
        return "safe"


def explain_result(
    score_result: ScoreResult,
    rule_result: RuleResult,
    content: Optional[str] = None,
    language: str = "zh",
    platform: str = "",
) -> str:
    """Generate a one-sentence explanation based on scoring results.

    Args:
        score_result: The complete scoring result with overall_score and dimensions.
        rule_result: The rule engine result with matched_rules and dimension_overrides.
        content: Optional original text content for keyword quoting with line numbers.
        language: Language code for output. "zh" for Chinese (default), "en" for English.
        platform: Detected platform name for platform-specific context.

    Returns:
        A string with emoji prefix explaining the scoring verdict.
    """
    if language == "en":
        return _explain_result_en(score_result, rule_result, content)
    return _explain_result_zh(score_result, rule_result, content, platform=platform)


def _explain_result_en(
    score_result: ScoreResult,
    rule_result: RuleResult,
    content: Optional[str] = None,
) -> str:
    """Generate English explanation based on scoring results."""
    overall = score_result.overall_score
    matched = rule_result.matched_rules

    # Count signal types
    signals: list[str] = []

    if any(r.startswith("scam") for r in matched) or "credibility_unverifiable" in matched:
        signals.append("scam/fraud indicators")
    if any(r.startswith("advertorial") for r in matched) or any(
        r.startswith("platform_") and "patterns" in r for r in matched
    ):
        signals.append("promotional/advertorial content")
    if any(r.startswith("emotional") for r in matched):
        signals.append("emotional manipulation")
    if "ai_generated_signals" in matched:
        signals.append("AI-generated content")

    # Count non-combo rules
    non_combo_count = len([r for r in matched if not r.startswith("combo_")])

    if overall >= 70:
        return "\u2705 Content looks legitimate, no obvious red flags."
    elif overall >= 40:
        if signals:
            details = ", ".join(signals)
            return f"\u26a0\ufe0f Suspicious signals detected: {details}. Exercise caution."
        return "\u26a0\ufe0f Content quality is uncertain. Consider cross-referencing with other sources."
    else:
        if signals:
            details = ", ".join(signals)
            return f"\U0001f6a8 High-risk content. Found {non_combo_count} rule violations: {details}."
        return "\U0001f6a8 High-risk content. No known patterns matched, but score is very low."


def _explain_result_zh(
    score_result: ScoreResult,
    rule_result: RuleResult,
    content: Optional[str] = None,
    platform: str = "",
) -> str:
    """Generate a one-sentence Chinese explanation based on scoring results."""
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
        base = "\U0001f914 信号不够明确。建议结合其他信息源判断，不要完全依赖单一评分。"
        return _append_context_and_confidence(base, platform, matched, score_result)

    # Count total matched rules (excluding combos for display)
    non_combo_count = len([r for r in matched if not r.startswith("combo_")])

    # Generate explanation based on score tier
    if overall >= 70:
        # Good content
        if signals:
            detail = f"，但有轻微信号：{'；'.join(signals)}"
        else:
            detail = "，论证清晰，信息密度较高"
        base = f"\u2705 内容质量正常{detail}。"
        return _append_context_and_confidence(base, platform, matched, score_result)

    elif overall >= 40:
        # Borderline content
        if signals:
            detail = "；".join(signals)
            base = f"\u26a0\ufe0f 内容存在风险信号。{detail}，建议人工复核。"
        else:
            base = "\u26a0\ufe0f 规则引擎未发现明显信号，得分偏低，建议人工复查或使用 LLM 深度分析。"
        return _append_context_and_confidence(base, platform, matched, score_result)

    else:
        # Junk / high-risk content
        if signals:
            detail = "；".join(signals)
            rule_count = non_combo_count
            if rule_count > 0:
                base = f"\U0001f6a8 高风险内容。命中 {rule_count} 条规则：{detail}。"
            else:
                base = f"\U0001f6a8 高风险内容。{detail}。"
        else:
            base = "\U0001f6a8 高风险内容。未匹配到已知模式，建议人工复查或启用 LLM 深度分析。"
        return _append_context_and_confidence(base, platform, matched, score_result)


def _append_context_and_confidence(
    base: str,
    platform: str,
    matched_rules: list[str],
    score_result: ScoreResult,
) -> str:
    """Append platform context and confidence language to base explanation.

    Args:
        base: The base explanation string.
        platform: Detected platform name.
        matched_rules: List of matched rule names.
        score_result: The scoring result (for confidence and signal count).

    Returns:
        The explanation with platform context and confidence language appended.
    """
    parts = [base]

    # Platform context
    ctx = _platform_context(platform, matched_rules)
    if ctx:
        parts.append(ctx)

    # Confidence language (only when there are signals)
    non_combo_count = len([r for r in matched_rules if not r.startswith("combo_")])
    if non_combo_count > 0:
        confidence = getattr(score_result, "confidence", 0) or 0
        conf_text = _confidence_language(confidence, non_combo_count)
        if conf_text:
            parts.append(conf_text)

    return " ".join(parts)
