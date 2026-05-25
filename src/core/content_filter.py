"""Content violation pre-filter — inspired by x-algorithm's VF Filter.

Catches obviously violating content before expensive LLM scoring.
Returns a FilterResult indicating whether content should be scored or rejected.

This runs BEFORE rules and LLM — costs zero tokens.
Focuses on OBVIOUS violations only (not borderline cases).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field


class FilterResult(BaseModel):
    """Result of content pre-filtering."""

    passed: bool = Field(..., description="Whether content passed the filter")
    violation_type: str | None = Field(default=None, description="Type of violation if rejected")
    violation_details: str | None = Field(default=None, description="Details about the violation")
    matched_patterns: list[str] = Field(default_factory=list, description="Patterns that triggered")


# ---------------------------------------------------------------------------
# Violation category definitions
# ---------------------------------------------------------------------------

# 1. Gambling (赌博) — online gambling promotion keywords
# Trigger: 2+ keywords present
_GAMBLING_KEYWORDS: list[str] = [
    "网上赌场",
    "在线博彩",
    "百家乐",
    "赌球",
    "开奖结果",
    "彩票预测",
    "赢钱技巧",
]

# 2. Pornographic (色情) — explicit sexual content keywords
# Trigger: 1+ keywords present
_PORNOGRAPHIC_KEYWORDS: list[str] = [
    "约炮",
    "裸聊",
    "色情直播",
    "成人视频",
    "一夜情",
]

# 3. Violence/Terrorism (暴力/恐怖) — graphic violence/gore promotion
# Trigger: 1+ keywords present
_VIOLENCE_KEYWORDS: list[str] = [
    "制作炸弹",
    "购买枪支",
    "恐怖袭击",
    "杀人方法",
]

# 4. Drug dealing (毒品) — drug dealing/promotion
# Trigger: 1+ keywords present
_DRUG_KEYWORDS: list[str] = [
    "购买毒品",
    "代购冰毒",
    "大麻出售",
    "迷药",
]

# 5. Phishing (钓鱼) — credential harvesting patterns
# Trigger: phishing phrase + URL pattern in same content
_PHISHING_PHRASES: list[str] = [
    "验证您的账号",
    "点击链接领取",
    "您的账户异常",
]

# Simple URL pattern for phishing detection (not overly strict)
_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")


# ---------------------------------------------------------------------------
# Individual category checks
# ---------------------------------------------------------------------------


def _check_gambling(text: str) -> FilterResult | None:
    """Check for gambling promotion content. Requires 2+ keyword matches."""
    matched = [kw for kw in _GAMBLING_KEYWORDS if kw in text]
    if len(matched) >= 2:
        return FilterResult(
            passed=False,
            violation_type="赌博",
            violation_details=f"检测到赌博推广内容，命中{len(matched)}个关键词",
            matched_patterns=matched,
        )
    return None


def _check_pornographic(text: str) -> FilterResult | None:
    """Check for pornographic content. Requires 1+ keyword match."""
    matched = [kw for kw in _PORNOGRAPHIC_KEYWORDS if kw in text]
    if len(matched) >= 1:
        return FilterResult(
            passed=False,
            violation_type="色情",
            violation_details=f"检测到色情内容，命中{len(matched)}个关键词",
            matched_patterns=matched,
        )
    return None


def _check_violence(text: str) -> FilterResult | None:
    """Check for violence/terrorism content. Requires 1+ keyword match."""
    matched = [kw for kw in _VIOLENCE_KEYWORDS if kw in text]
    if len(matched) >= 1:
        return FilterResult(
            passed=False,
            violation_type="暴力/恐怖",
            violation_details=f"检测到暴力恐怖内容，命中{len(matched)}个关键词",
            matched_patterns=matched,
        )
    return None


def _check_drugs(text: str) -> FilterResult | None:
    """Check for drug dealing content. Requires 1+ keyword match."""
    matched = [kw for kw in _DRUG_KEYWORDS if kw in text]
    if len(matched) >= 1:
        return FilterResult(
            passed=False,
            violation_type="毒品",
            violation_details=f"检测到毒品相关内容，命中{len(matched)}个关键词",
            matched_patterns=matched,
        )
    return None


def _check_phishing(text: str) -> FilterResult | None:
    """Check for phishing content. Requires phishing phrase + URL in same content."""
    matched_phrases = [phrase for phrase in _PHISHING_PHRASES if phrase in text]
    if matched_phrases and _URL_PATTERN.search(text):
        return FilterResult(
            passed=False,
            violation_type="钓鱼",
            violation_details="检测到钓鱼内容，包含诱导短语和链接",
            matched_patterns=matched_phrases,
        )
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_content(text: str) -> FilterResult:
    """Run all violation checks against content.

    Categories checked (in order):
    1. Gambling (赌博) — online gambling promotion keywords
    2. Pornographic (色情) — explicit sexual content keywords
    3. Violence (暴力) — graphic violence/gore promotion
    4. Drug-related (毒品) — drug dealing/promotion
    5. Phishing (钓鱼) — credential harvesting patterns

    Returns FilterResult with passed=False if ANY violation detected.
    Short-circuits on first violation found.
    """
    if not text or not text.strip():
        return FilterResult(passed=True)

    # Run checks in order of severity — short-circuit on first match
    checks = [
        _check_violence,
        _check_drugs,
        _check_pornographic,
        _check_gambling,
        _check_phishing,
    ]

    for check_fn in checks:
        result = check_fn(text)
        if result is not None:
            return result

    # All checks passed
    return FilterResult(passed=True)
