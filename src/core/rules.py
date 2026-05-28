"""Deterministic rules engine for junk-detector.

Fast, regex/keyword-based pattern matching to detect obvious content quality
signals without needing LLM calls. Rules fire independently and produce
dimension score overrides with associated confidence levels.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RuleResult(BaseModel):
    """Result of applying all rules against a piece of content."""

    matched_rules: list[str] = Field(default_factory=list, description="Names of rules that fired")
    dimension_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Dimension name -> score to override (e.g. {'scam_prob': 95})",
    )
    confidence: dict[str, float] = Field(
        default_factory=dict,
        description="Confidence per matched dimension (0-1)",
    )


@dataclass
class ComboRule:
    """A combo rule that fires when multiple weak signals co-occur.

    When all keywords in the set are present, apply score_boost and
    confidence_boost to the specified dimension.
    """

    name: str
    keywords: list[str] = field(default_factory=list)
    dimension: str = ""
    score_boost: float = 0.0
    confidence_boost: float = 0.0


# ---------------------------------------------------------------------------
# Scam / 韭菜收割 rules
# ---------------------------------------------------------------------------

_SCAM_KEYWORDS: list[str] = [
    # Original
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
    # Cryptocurrency scam
    "虚拟币",
    "币圈",
    "区块链投资",
    "数字货币",
    "挖矿赚钱",
    "合约交易",
    "炒币",
    "代币",
    "ICO",
    "数字黄金",
    "虚拟货币",
    "比特币投资",
    "以太坊投资",
    "币圈大佬",
    "空投",
    "质押挖矿",
    # Fake investment
    "理财课",
    "投资课程",
    "保本收益",
    "年化收益",
    "高收益零风险",
    "稳定收益",
    "内部渠道",
    "独家消息",
    "内幕消息",
    "投资内参",
    "股票推荐",
    "涨停板",
    "牛股推荐",
    "操盘手",
    # MLM
    "下线",
    "团队奖励",
    "推荐奖",
    "层级",
    "发展会员",
    "裂变",
    "拉人头",
    "上线",
    "代理招募",
    "管道收入",
    "团队分红",
    "直推奖",
    "级差奖",
    # General scam
    "一夜暴富",
    "轻松月入",
    "日赚",
    "翻倍",
    "白嫖",
    "免费送",
    "不花一分钱",
    "零投入",
    "保证赚钱",
    "包赚",
    "只赚不赔",
    "抢购",
    "秒杀",
    "抢到就是赚到",
    "暴利项目",
    "赚钱机器",
    "自动赚钱",
    "睡后收入",
    "躺着赚钱",
    "月入十万",
    "无本万利",
    "稳赚项目",
    "包教包会",
    "学完就能赚",
    "小白也能赚",
    "宝妈副业",
    "兼职日结",
    "手机赚钱",
    "在家赚钱",
    "不用上班",
]


def _build_keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Build a compiled regex pattern for a keyword.

    Short keywords (< 4 chars) that are ASCII/alphanumeric get word boundary
    matching to prevent false positives from substring matches within longer words.
    We use ASCII-letter-only lookarounds so that "ICO" matches next to Chinese
    characters but not inside "PICOT" or "Cisco".
    Chinese keywords and longer keywords use simple containment matching.
    """
    escaped = re.escape(keyword)
    # For short ASCII-only keywords, add ASCII-letter boundaries
    if len(keyword) < 4 and keyword.isascii():
        return re.compile(r"(?<![A-Za-z])" + escaped + r"(?![A-Za-z])", re.IGNORECASE)
    return re.compile(escaped)


# Pre-compile all scam keyword patterns at module load time
_SCAM_PATTERNS: list[re.Pattern[str]] = [_build_keyword_pattern(kw) for kw in _SCAM_KEYWORDS]


def _check_scam_keywords(content: str) -> Optional[tuple[float, float]]:
    """Check for scam/韭菜收割 keyword density.

    Returns (score, confidence) or None if not triggered.
    """
    hit_count = sum(1 for pattern in _SCAM_PATTERNS if pattern.search(content))

    if hit_count >= 3:
        return (95.0, 0.95)
    elif hit_count >= 1:
        return (75.0, 0.8)
    return None


# ---------------------------------------------------------------------------
# Emotional manipulation rules
# ---------------------------------------------------------------------------

_ANXIETY_PHRASES: list[str] = [
    # Original patterns
    "再不.*就晚了",
    "99%的人不知道",
    "震惊",
    "必看",
    "紧急",
    # FOMO
    "别人都在",
    "全网疯传",
    "百万人都在用",
    "错过就没了",
    "最后机会",
    "限时紧急",
    "不看后悔",
    "太晚了",
    "手慢无",
    "即将涨价",
    "马上截止",
    "爆款",
    "断货",
    "疯抢",
    "卖疯了",
    "火爆全网",
    "已有万人",
    "名额仅剩",
    "倒计时",
    # Clickbait
    "揭秘",
    "内幕",
    "真相",
    "惊人发现",
    "万万没想到",
    "细思极恐",
    "不转不是中国人",
    "看完沉默了",
    "转发保平安",
    "速看",
    "删前速看",
    "看到就是赚到",
    "不看亏大了",
    "惊呆了",
    "吓一跳",
    "后果不堪设想",
    "太可怕了",
    "赶紧收藏",
    "不收藏就找不到了",
    "建议收藏",
    "快转发给家人",
    "央视都报了",
    "官方紧急通知",
]

# Pre-compile anxiety patterns for performance
_ANXIETY_PATTERNS: list[re.Pattern[str]] = [re.compile(phrase) for phrase in _ANXIETY_PHRASES]


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
    # Original
    "推荐码",
    "优惠券",
    "折扣码",
    "点击链接",
    "复制口令",
    # Affiliate/influencer marketing
    "返利",
    "佣金",
    "分销",
    "带货",
    "种草",
    "好物推荐",
    "安利",
    "亲测有效",
    "良心推荐",
    "回购无数次",
    "闭眼入",
    "强烈推荐",
    "必买",
    "入手不亏",
    "同款",
    "同链接",
    "粉丝专属",
    "粉丝福利",
    "直播间",
    "专属优惠",
    "下单立减",
    # Additional commercial patterns
    "官方旗舰店",
    "限时秒杀",
    "满减",
    "拍下立减",
    "买一送一",
    "全网最低",
    "厂家直销",
    "一手货源",
    "招代理",
    "加盟",
    "合作共赢",
    "诚招",
    "批发价",
    "出厂价",
    "内部价",
    "员工价",
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
    "首先...其次...最后",
    "不容忽视",
    "众所周知",
    "毋庸置疑",
    "由此可见",
    "一言以蔽之",
    "在当今社会",
    "随着科技的发展",
    "不得不说",
    "客观来说",
    "换言之",
    "与此同时",
    "从某种程度上说",
    "事实上",
    "毫无疑问",
    "显而易见",
    "不难发现",
    "归根结底",
    "深入分析",
    "进一步来看",
    "从本质上讲",
    "就目前而言",
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
    chars = [c for c in content if c.strip() and c not in "，。！？、；：（）【】《》…—·"]
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
# Platform-specific patterns
# ---------------------------------------------------------------------------

_WECHAT_PATTERNS: list[str] = [
    "点击关注", "转发有礼", "阅读原文领取", "长按识别二维码",
    "关注后回复", "置顶公众号", "星标公众号", "公众号后台",
    "扫码关注", "点击阅读原文",
]

_XIAOHONGSHU_PATTERNS: list[str] = [
    "姐妹们", "绝绝子", "yyds", "无广", "自用推荐",
    "亲测好用", "回购N次", "平替", "合集", "避雷",
    "真的绝了", "谁懂啊", "天花板", "入股不亏",
]

_ZHIHU_PATTERNS: list[str] = [
    "谢邀", "利益相关", "人在美国", "匿了",
    "先问是不是", "强答一波", "泻药", "以上",
]

_DOUYIN_PATTERNS: list[str] = [
    "点赞关注", "评论区见", "双击666", "家人们",
    "老铁们", "点击小黄车", "直播间", "憋走",
    "关注不迷路", "粉丝宝宝", "三连",
]


def check_platform_patterns(content: str) -> dict[str, int]:
    """Check content for platform-specific engagement/promotion patterns.

    Returns dict of {platform_name: hit_count} for platforms with at least 1 hit.
    """
    results = {}
    patterns_map = {
        "wechat": _WECHAT_PATTERNS,
        "xiaohongshu": _XIAOHONGSHU_PATTERNS,
        "zhihu": _ZHIHU_PATTERNS,
        "douyin": _DOUYIN_PATTERNS,
    }
    for platform, patterns in patterns_map.items():
        hits = sum(1 for p in patterns if p in content)
        if hits > 0:
            results[platform] = hits
    return results


# ---------------------------------------------------------------------------
# Combo rules - multiple weak signals boosting confidence
# ---------------------------------------------------------------------------

_COMBO_RULES: list[ComboRule] = [
    ComboRule(
        name="engagement_bait",
        keywords=["关注", "点赞", "转发"],
        dimension="advertorial_prob",
        score_boost=20,
        confidence_boost=0.1,
    ),
    ComboRule(
        name="crypto_scam_combo",
        keywords=["币圈", "翻倍", "稳赚"],
        dimension="scam_prob",
        score_boost=15,
        confidence_boost=0.1,
    ),
    ComboRule(
        name="fomo_urgency",
        keywords=["限时", "名额", "最后"],
        dimension="emotional_manipulation",
        score_boost=15,
        confidence_boost=0.1,
    ),
]

# Pre-compile combo keyword patterns at module load time for consistency
# with the word-boundary-aware matching used for individual scam keywords.
_COMBO_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    combo.name: [_build_keyword_pattern(kw) for kw in combo.keywords] for combo in _COMBO_RULES
}


def _check_combo_rules(content: str, result: RuleResult) -> None:
    """Check combo rules and apply boosts to existing dimension scores.

    Combo rules fire when ALL keywords in the combo set are present.
    Boosts are additive to existing scores and capped at 100.
    Confidence boosts are additive and capped at 1.0.
    """
    for combo in _COMBO_RULES:
        patterns = _COMBO_PATTERNS[combo.name]
        if all(pattern.search(content) for pattern in patterns):
            rule_name = f"combo_{combo.name}"
            result.matched_rules.append(rule_name)

            # Apply score boost (additive, capped at 100)
            current_score = result.dimension_overrides.get(combo.dimension, 0.0)
            new_score = min(current_score + combo.score_boost, 100.0)
            result.dimension_overrides[combo.dimension] = new_score

            # Apply confidence boost (additive, capped at 1.0)
            current_conf = result.confidence.get(combo.dimension, 0.0)
            new_conf = min(current_conf + combo.confidence_boost, 1.0)
            result.confidence[combo.dimension] = new_conf


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def should_skip_llm(rule_result: RuleResult, content_text: str) -> tuple[bool, str]:
    """Determine if rules are confident enough to skip the LLM call.

    Logic:
    - Count distinct non-combo rules matched (strong signals from multiple categories).
    - If >= 3 distinct non-combo rules matched AND average confidence across all
      matched dimensions >= 0.85: return (True, "high_confidence_rules").
    - If 0 keywords matched AND content is long (> 1000 chars): return
      (False, "clean_prose_needs_llm") -- clean text still needs LLM analysis.
    - Default: return (False, "insufficient_confidence").

    Args:
        rule_result: The RuleResult from apply_rules().
        content_text: The original content text.

    Returns:
        Tuple of (should_skip: bool, reason: str).
    """
    # Count non-combo rules
    non_combo_rules = [r for r in rule_result.matched_rules if not r.startswith("combo_")]
    non_combo_count = len(non_combo_rules)

    # Special case: no rules matched at all
    if non_combo_count == 0:
        if len(content_text) > 1000:
            return (False, "clean_prose_needs_llm")
        return (False, "insufficient_confidence")

    # High-confidence single dimension: if any dimension has score >= 90 and confidence >= 0.9,
    # the rules are confident enough on their own
    for dim, score in rule_result.dimension_overrides.items():
        conf = rule_result.confidence.get(dim, 0)
        if score >= 90 and conf >= 0.9:
            return (True, "high_confidence_single_dimension")

    # Check if we have >= 3 distinct non-combo rules with high average confidence
    if non_combo_count >= 3:
        # Only average confidence values >= 0.7 to exclude dimensions that were
        # only set by combo rules (combo boosts start at 0.1 confidence, so a
        # combo-only dimension would have low confidence).
        confidences = [c for c in rule_result.confidence.values() if c >= 0.7]
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            if avg_confidence >= 0.85:
                return (True, "high_confidence_rules")

    return (False, "insufficient_confidence")


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

    # --- Combo rules (must run after individual checks) ---
    _check_combo_rules(content, result)

    # --- Platform-specific patterns ---
    platform_hits = check_platform_patterns(content)
    for platform, hits in platform_hits.items():
        if hits >= 2:
            rule_name = f"platform_{platform}_patterns"
            result.matched_rules.append(rule_name)
            # Boost advertorial_prob by +15, capped at 100
            current_score = result.dimension_overrides.get("advertorial_prob", 0.0)
            new_score = min(current_score + 15.0, 100.0)
            result.dimension_overrides["advertorial_prob"] = new_score
            # Set confidence to 0.7 (or keep existing if higher)
            current_conf = result.confidence.get("advertorial_prob", 0.0)
            result.confidence["advertorial_prob"] = max(current_conf, 0.7)

    # --- Custom rules (user-defined) ---
    try:
        from src.core.custom_rules import apply_custom_rules, load_custom_rules
        custom_rules = load_custom_rules()
        if custom_rules:
            custom_result = apply_custom_rules(content, custom_rules)
            # Merge custom results
            result.matched_rules.extend(custom_result.matched_rules)
            for dim, score_val in custom_result.dimension_overrides.items():
                current = result.dimension_overrides.get(dim, 0)
                result.dimension_overrides[dim] = min(current + score_val, 100.0)
            for dim, conf in custom_result.confidence.items():
                current = result.confidence.get(dim, 0)
                result.confidence[dim] = max(current, conf)
    except (ImportError, OSError, ValueError) as e:
        logger.warning("Failed to load/apply custom rules: %s", e)

    return result
