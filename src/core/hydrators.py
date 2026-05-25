"""Content hydrators — enrich scoring context with additional metadata.

Inspired by x-algorithm's Query Hydrators and Candidate Hydrators which attach
features to candidates before scoring/ranking. We attach metadata to content
before it goes through the scoring pipeline.

Each hydrator is an async function that takes a PipelineContext and returns
a dict of metadata to merge into ctx.metadata.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


async def hydrate_source_reputation(
    ctx: "PipelineContext",  # noqa: F821
    db_path: str = "junk_detector.db",
) -> dict[str, Any]:
    """Look up historical scores for this content's domain/source.

    Queries storage for all previously scored articles from the same domain,
    then computes the average overall_score as a reputation signal.

    Returns:
        Dict with keys:
        - source_domain: extracted domain string (or None)
        - source_reputation: average overall_score for this domain (0-100, or None)
        - source_article_count: number of previously scored articles from this domain
    """
    from src.storage.db import query as db_query

    result: dict[str, Any] = {
        "source_domain": None,
        "source_reputation": None,
        "source_article_count": 0,
    }

    # Extract domain from source_url
    source_url = None
    if ctx.content and ctx.content.source_url:
        source_url = ctx.content.source_url

    if not source_url:
        return result

    try:
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower()
        # Strip www. prefix for consistency
        if domain.startswith("www."):
            domain = domain[4:]
        result["source_domain"] = domain
    except Exception:
        return result

    if not domain:
        return result

    # Query all scores from this domain
    try:
        # Get a generous limit of historical scores for this domain
        all_scores = await asyncio.to_thread(db_query, None, 1000, db_path)

        # Filter to same domain
        domain_scores = []
        for record in all_scores:
            record_url = record.get("source_url", "")
            if not record_url:
                continue
            try:
                record_domain = urlparse(record_url).netloc.lower()
                if record_domain.startswith("www."):
                    record_domain = record_domain[4:]
                if record_domain == domain:
                    domain_scores.append(record["overall_score"])
            except Exception:
                continue

        if domain_scores:
            result["source_reputation"] = round(
                sum(domain_scores) / len(domain_scores), 1
            )
            result["source_article_count"] = len(domain_scores)

    except Exception as e:
        logger.warning(f"Failed to query source reputation for {domain}: {e}")

    return result


async def hydrate_article_stats(
    ctx: "PipelineContext",  # noqa: F821
) -> dict[str, Any]:
    """Compute basic article statistics for enrichment.

    Returns:
        Dict with keys:
        - char_count: total character count
        - paragraph_count: number of paragraphs (text blocks separated by newlines)
        - link_count: number of URLs found in the text
        - image_references: count of image-like references (markdown images, img tags)
        - avg_sentence_length: average sentence length in characters
        - has_links: whether the article contains external links
    """
    result: dict[str, Any] = {
        "char_count": 0,
        "paragraph_count": 0,
        "link_count": 0,
        "image_references": 0,
        "avg_sentence_length": 0.0,
        "has_links": False,
    }

    text = ""
    if ctx.content:
        text = ctx.content.text
    elif ctx.raw_input:
        text = ctx.raw_input

    if not text:
        return result

    # Character count
    result["char_count"] = len(text)

    # Paragraph count (non-empty lines separated by blank lines)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    result["paragraph_count"] = len(paragraphs)

    # Link count (URLs)
    url_pattern = re.compile(r"https?://[^\s\)\]]+")
    urls = url_pattern.findall(text)
    result["link_count"] = len(urls)
    result["has_links"] = len(urls) > 0

    # Image references (markdown ![...](...) or <img ... />)
    img_markdown = re.findall(r"!\[.*?\]\(.*?\)", text)
    img_html = re.findall(r"<img\s", text, re.IGNORECASE)
    result["image_references"] = len(img_markdown) + len(img_html)

    # Average sentence length
    # Split by common sentence-ending punctuation (handles Chinese and English)
    sentences = re.split(r"[。！？.!?\n]+", text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 2]
    if sentences:
        total_chars = sum(len(s) for s in sentences)
        result["avg_sentence_length"] = round(total_chars / len(sentences), 1)

    return result
