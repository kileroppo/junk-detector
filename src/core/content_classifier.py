"""Content type classifier - identifies article type for dynamic weight adjustment.

Uses rule-based heuristics (keyword matching + structural analysis) to classify
content into types, then returns weight adjustment multipliers for each type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ContentType(str, Enum):
    TOOL_LIST = "tool_list"
    TUTORIAL = "tutorial"
    OPINION = "opinion"
    NEWS = "news"
    ADVERTORIAL = "advertorial"
    PERSONAL_STORY = "personal"
    ACADEMIC = "academic"
    AI_GENERATED = "ai_generated"
    UNKNOWN = "unknown"


TYPE_LABELS_ZH: dict[ContentType, str] = {
    ContentType.TOOL_LIST: "工具列表/资源汇总",
    ContentType.TUTORIAL: "教程/操作指南",
    ContentType.OPINION: "观点/评论",
    ContentType.NEWS: "新闻报道",
    ContentType.ADVERTORIAL: "软文/推广",
    ContentType.PERSONAL_STORY: "个人故事/经历",
    ContentType.ACADEMIC: "学术/研究",
    ContentType.AI_GENERATED: "AI批量生成",
    ContentType.UNKNOWN: "未知类型",
}

WEIGHT_ADJUSTMENTS: dict[ContentType, dict[str, float]] = {
    ContentType.TOOL_LIST: {"originality": 0.5, "info_density": 1.5, "reasoning_quality": 0.3},
    ContentType.TUTORIAL: {"readability": 1.5, "info_density": 1.3, "advertorial_prob": -1.5},
    ContentType.OPINION: {"reasoning_quality": 1.5, "originality": 1.3, "info_density": 0.7},
    ContentType.NEWS: {"timeliness": 1.5, "emotional_manipulation": -1.5, "originality": 0.5},
    ContentType.ADVERTORIAL: {"advertorial_prob": -2.0, "scam_prob": -1.5},
    ContentType.PERSONAL_STORY: {
        "originality": 1.3,
        "emotional_manipulation": -0.5,
        "readability": 1.2,
    },
    ContentType.ACADEMIC: {"reasoning_quality": 1.5, "info_density": 1.5, "readability": 0.7},
    ContentType.AI_GENERATED: {"ai_generated_prob": -1.5, "originality": 0.3},
    ContentType.UNKNOWN: {},
}

# Keywords for each content type
_KEYWORDS: dict[ContentType, list[str]] = {
    ContentType.TOOL_LIST: [
        "推荐",
        "工具",
        "合集",
        "盘点",
        "清单",
        "TOP",
        "top",
        "排行",
        "榜单",
        "必备",
        "神器",
        "利器",
        "资源",
        "汇总",
        "整理",
    ],
    ContentType.TUTORIAL: [
        "如何",
        "教程",
        "步骤",
        "第一步",
        "第二步",
        "第三步",
        "操作指南",
        "实战",
        "手把手",
        "入门",
        "从零开始",
        "step",
    ],
    ContentType.OPINION: [
        "我认为",
        "我觉得",
        "观点",
        "看法",
        "个人认为",
        "我的理解",
        "依我看",
        "在我看来",
        "不得不说",
    ],
    ContentType.NEWS: [
        "记者",
        "报道",
        "消息",
        "据悉",
        "据了解",
        "新华社",
        "央视",
        "发布会",
        "官方",
        "通报",
        "公告",
    ],
    ContentType.ADVERTORIAL: [
        "推荐码",
        "优惠",
        "折扣",
        "限时",
        "立减",
        "券",
        "邀请码",
        "返利",
        "佣金",
        "下单",
        "购买链接",
    ],
    ContentType.PERSONAL_STORY: [
        "我的经历",
        "分享",
        "亲身",
        "回忆",
        "那年",
        "那时候",
        "记得",
        "经历过",
        "感悟",
        "心路历程",
    ],
    ContentType.ACADEMIC: [
        "研究表明",
        "数据显示",
        "实验",
        "方法论",
        "文献",
        "引用",
        "论文",
        "假设",
        "样本",
        "统计",
        "显著性",
    ],
    ContentType.AI_GENERATED: [
        "总而言之",
        "综上所述",
        "总的来说",
        "值得注意的是",
        "不可否认",
        "毋庸置疑",
    ],
}


@dataclass
class ClassificationResult:
    """Result of content type classification."""

    primary_type: ContentType
    confidence: float  # 0-1
    type_probabilities: dict[str, float] = field(default_factory=dict)
    weight_adjustments: dict[str, float] = field(default_factory=dict)
    type_label_zh: str = ""


def _count_keyword_matches(text: str, content_type: ContentType) -> int:
    """Count how many keywords for a given type appear in the text."""
    keywords = _KEYWORDS.get(content_type, [])
    count = 0
    for kw in keywords:
        if kw.lower() in text.lower():
            count += 1
    return count


def _analyze_structure(text: str) -> dict[str, float]:
    """Analyze structural features of the text.

    Returns feature scores that boost certain content types.
    """
    features: dict[str, float] = {}

    lines = text.split("\n")
    total_lines = max(len(lines), 1)

    # Count bullet points and numbered lists
    list_pattern = re.compile(r"^\s*[\-\*\•\d+\.]\s+")
    list_count = sum(1 for line in lines if list_pattern.match(line))
    features["list_density"] = list_count / total_lines

    # Count URLs/links
    url_pattern = re.compile(r"https?://\S+")
    url_count = len(url_pattern.findall(text))
    features["url_count"] = min(url_count / 5.0, 1.0)  # normalize to 0-1

    # Count code blocks
    code_pattern = re.compile(r"```")
    code_count = len(code_pattern.findall(text))
    features["code_blocks"] = min(code_count / 4.0, 1.0)

    # Paragraph length uniformity (AI-generated tends to be uniform)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 2:
        lengths = [len(p) for p in paragraphs]
        avg_len = sum(lengths) / len(lengths)
        if avg_len > 0:
            variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
            cv = (variance**0.5) / avg_len  # coefficient of variation
            features["paragraph_uniformity"] = max(0, 1.0 - cv)
        else:
            features["paragraph_uniformity"] = 0.0
    else:
        features["paragraph_uniformity"] = 0.0

    # First person usage
    first_person_count = len(re.findall(r"我[的了们]?", text))
    features["first_person"] = min(first_person_count / 10.0, 1.0)

    return features


def classify_content(text: str) -> ClassificationResult:
    """Classify content into a type using rule-based heuristics.

    Pipeline:
        1. Count keyword matches for each type
        2. Analyze structural features
        3. Compute weighted scores per type
        4. Return highest-probability type with weight adjustments

    Args:
        text: The content text to classify.

    Returns:
        ClassificationResult with type, confidence, and weight adjustments.
    """
    if not text or not text.strip():
        return ClassificationResult(
            primary_type=ContentType.UNKNOWN,
            confidence=0.0,
            type_probabilities={t.value: 0.0 for t in ContentType},
            weight_adjustments={},
            type_label_zh=TYPE_LABELS_ZH[ContentType.UNKNOWN],
        )

    # 1. Count keyword matches
    keyword_scores: dict[ContentType, float] = {}
    for ct in ContentType:
        if ct == ContentType.UNKNOWN:
            continue
        keyword_scores[ct] = _count_keyword_matches(text, ct)

    # 2. Analyze structural features
    features = _analyze_structure(text)

    # 3. Apply structural bonuses
    # Tool list: high list density + many URLs
    keyword_scores[ContentType.TOOL_LIST] += features["list_density"] * 5
    keyword_scores[ContentType.TOOL_LIST] += features["url_count"] * 3

    # Tutorial: code blocks + list structure
    keyword_scores[ContentType.TUTORIAL] += features["code_blocks"] * 4
    keyword_scores[ContentType.TUTORIAL] += features["list_density"] * 2

    # Opinion: first person usage
    keyword_scores[ContentType.OPINION] += features["first_person"] * 3

    # Personal story: first person + less structured
    keyword_scores[ContentType.PERSONAL_STORY] += features["first_person"] * 2

    # AI generated: paragraph uniformity
    keyword_scores[ContentType.AI_GENERATED] += features["paragraph_uniformity"] * 4

    # 4. Normalize to probabilities
    total_score = sum(keyword_scores.values())
    if total_score == 0:
        return ClassificationResult(
            primary_type=ContentType.UNKNOWN,
            confidence=0.0,
            type_probabilities={t.value: 0.0 for t in ContentType},
            weight_adjustments={},
            type_label_zh=TYPE_LABELS_ZH[ContentType.UNKNOWN],
        )

    type_probabilities: dict[str, float] = {}
    for ct, score in keyword_scores.items():
        type_probabilities[ct.value] = round(score / total_score, 3)

    # Find the top type
    best_type = max(keyword_scores, key=keyword_scores.get)  # type: ignore[arg-type]
    best_score = keyword_scores[best_type]
    confidence = min(best_score / max(total_score, 1), 1.0)

    # If confidence is very low (no clear winner), return UNKNOWN
    if confidence < 0.15 or best_score < 1.5:
        return ClassificationResult(
            primary_type=ContentType.UNKNOWN,
            confidence=confidence,
            type_probabilities=type_probabilities,
            weight_adjustments={},
            type_label_zh=TYPE_LABELS_ZH[ContentType.UNKNOWN],
        )

    weight_adjustments = WEIGHT_ADJUSTMENTS.get(best_type, {})

    return ClassificationResult(
        primary_type=best_type,
        confidence=round(confidence, 3),
        type_probabilities=type_probabilities,
        weight_adjustments=weight_adjustments,
        type_label_zh=TYPE_LABELS_ZH[best_type],
    )
