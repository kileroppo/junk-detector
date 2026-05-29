"""Query expansion module - use LLM to generate keyword variants and synonyms.

Sun Zi: yi zheng he, yi qi sheng - existing keywords are the regular army,
expanded variants are the surprise flanking force.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "junk-detector"
_CACHE_FILE = _CACHE_DIR / "expansions.json"

_EXPANSION_PROMPT = """你是一个中文内容审核专家。请为以下关键词生成3-5个变体/同义词/混淆写法。

要求：
1. 包含同义替换（如"日入过万" → "日赚万元"）
2. 包含口语变体（如"加微信" → "加v", "加wx"）
3. 包含数字/符号混淆（如"月入百万" → "月入100w", "月入bw"）
4. 保持语义等价，确保变体仍表达相同含义

关键词列表：
{keywords}

请以JSON格式输出，格式为：
{{"keyword1": ["variant1", "variant2", "variant3"], "keyword2": ["variant1", "variant2"]}}

只输出JSON，不要其他文字。"""


def _load_cache() -> dict[str, list[str]]:
    """Load expansion cache from disk."""
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load expansion cache: %s", e)
    return {}


def _save_cache(cache: dict[str, list[str]]) -> None:
    """Save expansion cache to disk."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _CACHE_FILE.chmod(0o600)
    except OSError as e:
        logger.warning("Failed to save expansion cache: %s", e)


def _cache_key(keywords: list[str]) -> str:
    """Generate a cache key from keyword list."""
    return hashlib.md5("|".join(sorted(keywords)).encode()).hexdigest()


async def _call_llm(prompt: str, model: str) -> str:
    """Call LLM via litellm for expansion."""
    from litellm import acompletion

    response = await acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2000,
    )
    return response.choices[0].message.content or ""


async def expand_keywords(
    keywords: list[str],
    model: str = "deepseek/deepseek-chat",
    use_cache: bool = True,
) -> dict[str, list[str]]:
    """Expand keywords into variants using LLM.

    Args:
        keywords: List of keywords to expand.
        model: LLM model to use for expansion.
        use_cache: Whether to use file-based cache.

    Returns:
        Dict mapping original keywords to lists of variant strings.
        Returns empty dict on failure (silent failure with logging).
    """
    if not keywords:
        return {}

    # Check cache
    if use_cache:
        cache = _load_cache()
        key = _cache_key(keywords)
        if key in cache:
            logger.info("Using cached expansions for %d keywords", len(keywords))
            return cache[key]

    # Call LLM
    try:
        prompt = _EXPANSION_PROMPT.format(
            keywords="\n".join(f"- {kw}" for kw in keywords)
        )
        response_text = await _call_llm(prompt, model)

        # Parse JSON from response
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
        else:
            result = json.loads(response_text)

        # Validate structure
        if not isinstance(result, dict):
            logger.warning("LLM returned non-dict response")
            return {}

        # Ensure all values are lists of strings
        cleaned: dict[str, list[str]] = {}
        for k, v in result.items():
            if isinstance(v, list):
                cleaned[k] = [str(item) for item in v]

        # Save to cache
        if use_cache and cleaned:
            cache = _load_cache()
            cache[_cache_key(keywords)] = cleaned
            _save_cache(cache)

        return cleaned

    except Exception as e:
        logger.error("Keyword expansion failed: %s", e)
        return {}


def expand_keywords_sync(
    keywords: list[str],
    model: str = "deepseek/deepseek-chat",
    use_cache: bool = True,
) -> dict[str, list[str]]:
    """Synchronous wrapper for expand_keywords."""
    return asyncio.run(expand_keywords(keywords, model=model, use_cache=use_cache))
