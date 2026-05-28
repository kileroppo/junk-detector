"""Content optimizer — smart truncation for LLM token savings."""

from __future__ import annotations

import hashlib
import random

# Keywords that indicate suspicious/scam/manipulative content
_SUSPICIOUS_KEYWORDS = [
    # Scam indicators
    "日入过万",
    "躺赚",
    "财富自由",
    "稳赚不赔",
    "零成本",
    "免费领取",
    "限时",
    "名额有限",
    "最后一天",
    "私聊",
    "加微信",
    "暴富",
    "割韭菜",
    "翻倍",
    "保本",
    "内部消息",
    # Emotional manipulation
    "震惊",
    "不转不是",
    "必看",
    "细思极恐",
    "惊天",
    "真相",
    "黑幕",
    "恐怖",
    "崩溃",
    "愤怒",
    # Advertorial signals
    "推荐码",
    "优惠券",
    "折扣",
    "返利",
    "邀请码",
    "注册链接",
    "下单",
    "购买",
]


def _score_paragraph(paragraph: str) -> int:
    """Score a paragraph by counting suspicious keyword occurrences."""
    count = 0
    lower_para = paragraph.lower()
    for kw in _SUSPICIOUS_KEYWORDS:
        if kw in lower_para:
            count += 1
    return count


def smart_truncate(text: str, max_chars: int = 1500) -> str:
    """Truncate long text by extracting key segments.

    If text is shorter than max_chars, returns it unchanged.
    Otherwise extracts:
    - First 200 chars (opening context)
    - Last 200 chars (closing context)
    - Most suspicious paragraph (highest keyword density)
    - Random 200-char sample from the middle

    Joins with '\\n[...]\\n' separators, capped at max_chars.

    Args:
        text: The input text to potentially truncate.
        max_chars: Maximum character count for the output.

    Returns:
        The original text if short enough, or a truncated version.
    """
    if len(text) <= max_chars:
        return text

    separator = "\n[...]\n"

    # Extract segments
    first_segment = text[:200]
    last_segment = text[-200:]

    # Find the most suspicious paragraph
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text[i : i + 200] for i in range(0, len(text), 200)]

    # Score paragraphs and pick the most suspicious one
    best_para = ""
    best_score = -1
    for para in paragraphs:
        s = _score_paragraph(para)
        if s > best_score:
            best_score = s
            best_para = para

    # Cap suspicious paragraph at 300 chars
    suspicious_segment = best_para[:300] if best_para else ""

    # Deterministic 200-char sample from the middle (avoid overlap with first/last)
    # Seed from content hash so same input always produces same output
    middle_start = 200
    middle_end = max(len(text) - 200, middle_start + 1)
    if middle_end - middle_start > 200:
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        start_pos = rng.randint(middle_start, middle_end - 200)
        middle_segment = text[start_pos : start_pos + 200]
    else:
        middle_segment = text[middle_start:middle_end]

    # Join segments
    segments = [first_segment, suspicious_segment, middle_segment, last_segment]
    # Remove empty segments
    segments = [s for s in segments if s]
    result = separator.join(segments)

    # Cap total at max_chars
    if len(result) > max_chars:
        result = result[:max_chars]

    return result
