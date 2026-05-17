"""Content summarizer for scoring optimization.

Inspired by Grox's summarizer pattern in x-algorithm. Long articles (>5000 chars)
are summarized before scoring to reduce token consumption (~60-70% savings) while
preserving all quality signals needed for accurate scoring.
"""

from __future__ import annotations

import logging

import litellm

logger = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """你是一个内容分析助手。请对以下长文进行压缩摘要，保留以下特征用于后续质量评分：
1. 文章的核心论点和关键信息
2. 写作风格和语气（如有情绪操纵/标题党，保留原文表述）
3. 任何推广、广告或商业意图的痕迹
4. 任何可疑的承诺或诱导性表述
5. 论证的逻辑结构（是否有数据/引用支撑）

注意：不要美化或清理原文的问题表述，保留原始特征以便评分。
输出压缩后的文本，约2000-3000字。

原文：
{content}"""


def _fallback_truncate(content: str) -> str:
    """Simple truncation fallback: first 2000 chars + ... + last 1000 chars."""
    return content[:2000] + "\n...\n" + content[-1000:]


async def summarize_for_scoring(
    content: str,
    model: str = "deepseek/deepseek-chat",
    max_chars: int = 5000,
) -> str:
    """Summarize long content for scoring, preserving quality signals.

    If content is short enough, returns it unchanged. For long content,
    calls LLM to produce a scoring-optimized summary that retains all
    signals relevant to quality evaluation (manipulative language, promotional
    content, factual claims, tone, etc.).

    Args:
        content: The text content to potentially summarize.
        model: LLM model to use for summarization.
        max_chars: Threshold above which summarization is triggered.

    Returns:
        Original content if short enough, or a condensed summary (~2000-3000 chars)
        that retains all quality signals for scoring.
    """
    if len(content) <= max_chars:
        return content

    prompt = _SUMMARIZE_PROMPT.replace("{content}", content)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=2048,
        )

        summary = response.choices[0].message.content
        if not summary or not summary.strip():
            logger.warning("LLM returned empty summary, falling back to truncation")
            return _fallback_truncate(content)

        return summary.strip()

    except Exception as e:
        logger.warning(
            "Summarization LLM call failed (%s), falling back to truncation", e
        )
        return _fallback_truncate(content)
