"""Default pipeline stages for junk-detector.

Each stage is an async function: PipelineContext → PipelineContext.
Stages are designed to be composable — you can replace or skip any stage
without breaking the pipeline.
"""

from __future__ import annotations

import logging

from src.core.pipeline import PipelineContext

logger = logging.getLogger(__name__)


async def extract_stage(ctx: PipelineContext) -> PipelineContext:
    """Extract content from input (URL, text, or file).

    Uses the appropriate extractor based on ctx.input_type:
    - "url": fetches and parses web page (uses smart_extract for SPA support if available)
    - "text": wraps raw text into Content model
    - "file": reads file from disk

    This is a critical stage — pipeline halts if extraction fails.
    """
    from src.extractors.web import extract_from_url
    from src.extractors.text import extract_from_text, extract_from_file

    # Try to import smart_extract for SPA support
    try:
        from src.extractors.playwright_web import smart_extract
        _has_smart_extract = True
    except ImportError:
        _has_smart_extract = False

    if ctx.input_type == "url":
        if _has_smart_extract:
            ctx.content = await smart_extract(ctx.raw_input)
        else:
            ctx.content = await extract_from_url(ctx.raw_input)
    elif ctx.input_type == "file":
        ctx.content = extract_from_file(ctx.raw_input)
    else:
        # Default to text extraction
        ctx.content = extract_from_text(ctx.raw_input)

    return ctx


async def enrich_stage(ctx: PipelineContext) -> PipelineContext:
    """Enrich content with metadata (inspired by x-algorithm's Query Hydrator).

    Runs all hydrators and merges their results into ctx.metadata.
    Individual hydrator failures are logged but don't block the pipeline.

    Adds:
    - source_reputation: historical average score for this domain
    - source_article_count: number of previously scored articles from this domain
    - similar_articles: list of similar previously-scored articles
    - max_similarity: highest similarity score found
    - char_count, paragraph_count, link_count, etc: article statistics
    """
    from src.core.hydrators import (
        hydrate_source_reputation,
        hydrate_article_stats,
    )

    # Run hydrators — each returns a dict to merge into metadata
    hydrators = [
        ("source_reputation", hydrate_source_reputation),
        ("article_stats", hydrate_article_stats),
    ]

    for hydrator_name, hydrator_fn in hydrators:
        try:
            if hydrator_name == "source_reputation":
                result = await hydrator_fn(ctx, db_path=_get_db_path(ctx))
            else:
                result = await hydrator_fn(ctx)
            ctx.metadata.update(result)
        except Exception as e:
            logger.warning(f"Hydrator '{hydrator_name}' failed: {e}")
            ctx.errors.append(f"enrich/{hydrator_name}: {e}")

    # Check for similar content via fingerprint (fast, zero-cost)
    try:
        from src.core.content_fingerprint import find_similar
        if ctx.content and ctx.content.text:
            similar = find_similar(ctx.content.text, threshold=5)
            if similar:
                ctx.metadata["fingerprint_matches"] = [
                    {"title": m.title, "similarity": m.similarity, "distance": m.hamming_distance}
                    for m in similar[:5]  # top 5 matches
                ]
                logger.info(f"Fingerprint: found {len(similar)} similar article(s)")
    except Exception as e:
        logger.debug(f"Fingerprint check failed: {e}")

    return ctx


async def preprocess_stage(ctx: PipelineContext) -> PipelineContext:
    """Preprocess content before scoring.

    - Long articles get summarized (uses summarizer model) to stay within
      LLM context limits and improve scoring accuracy
    - Very short content is flagged in metadata
    - Sets ctx.processed_text to the text that will actually be scored
    """
    if ctx.content is None:
        ctx.processed_text = ctx.raw_input
        return ctx

    text = ctx.content.text
    config = ctx.config

    # Flag very short content
    if len(text) < 100:
        ctx.metadata["short_content"] = True
        ctx.processed_text = text
        return ctx

    # Summarize long articles if enabled
    if config.summarize_enabled and len(text) > config.summarize_max_chars:
        try:
            summarized = await _summarize_text(text, config)
            ctx.processed_text = summarized
            ctx.metadata["was_summarized"] = True
            ctx.metadata["original_length"] = len(text)
            ctx.metadata["summarized_length"] = len(summarized)
        except Exception as e:
            logger.warning(f"Summarization failed, using truncated text: {e}")
            # Fallback: use first N chars
            ctx.processed_text = text[: config.summarize_max_chars]
            ctx.metadata["was_truncated"] = True
    else:
        ctx.processed_text = text

    return ctx


async def score_stage(ctx: PipelineContext) -> PipelineContext:
    """Run the actual scoring (rules + LLM judge).

    Calls the existing scorer.score() function which handles:
    - Deterministic rules
    - LLM judge (primary model)
    - Confidence-based fallback to secondary model
    - Rule overrides on LLM results
    - Overall score calculation with weights
    - Label generation

    This is a critical stage — pipeline halts if scoring fails.
    """
    from src.core.scorer import score

    # Use processed_text if available, otherwise fall back to content text
    text_to_score = ctx.processed_text
    if text_to_score is None and ctx.content:
        text_to_score = ctx.content.text
    if text_to_score is None:
        text_to_score = ctx.raw_input

    # Determine language from context metadata (set by preferences during enrich stage)
    language = ctx.metadata.get("language", "zh")

    ctx.result = await score(text_to_score, config=ctx.config, language=language)
    return ctx


async def postprocess_stage(ctx: PipelineContext) -> PipelineContext:
    """Post-processing: apply metadata adjustments and persist results.

    - If similar_articles found with high similarity, boost originality penalty
    - If source has historically low scores, add a note to summary
    - Save result + embedding to storage
    """
    if ctx.result is None:
        return ctx

    # --- Metadata-driven adjustments ---

    # Originality penalty for highly similar existing articles
    similar_articles = ctx.metadata.get("similar_articles", [])
    max_similarity = ctx.metadata.get("max_similarity", 0.0)
    if max_similarity >= 0.90:
        # Very high similarity — likely a copy/repost
        original_originality = ctx.result.dimensions.originality
        penalty = min(30, int((max_similarity - 0.85) * 200))
        new_originality = max(0, original_originality - penalty)
        ctx.result.dimensions.originality = new_originality
        ctx.metadata["originality_penalty_applied"] = penalty

        # Add label if not already present
        if "疑似搬运" not in ctx.result.labels:
            ctx.result.labels.append("疑似搬运")

    # Source reputation note
    source_reputation = ctx.metadata.get("source_reputation")
    if source_reputation is not None and source_reputation < 40:
        domain = ctx.metadata.get("source_domain", "unknown")
        note = f" [注: 来源 {domain} 历史平均分 {source_reputation}]"
        ctx.result.summary += note

    # Recalculate overall score if dimensions were adjusted
    if ctx.metadata.get("originality_penalty_applied"):
        from src.core.scorer import _calculate_overall

        ctx.result.overall_score = _calculate_overall(
            ctx.result.dimensions, ctx.config
        )

    # --- Source reputation blacklist/whitelist adjustment ---
    from src.core.source_reputation import get_source_adjustment

    domain = ctx.metadata.get("source_domain")
    adjustment, reason = get_source_adjustment(
        domain, db_path=_get_db_path(ctx)
    )
    if adjustment != 0:
        new_score = ctx.result.overall_score + adjustment
        ctx.result.overall_score = max(0, min(100, new_score))
        ctx.metadata["source_adjustment"] = adjustment
        ctx.metadata["source_adjustment_reason"] = reason

        # Add label
        if adjustment < 0:
            label = "黑名单来源"
        else:
            label = "可信来源"
        if label not in ctx.result.labels:
            ctx.result.labels.append(label)

        # Append reason to summary
        ctx.result.summary += f" [{reason}]"

    # --- Persist results ---
    try:
        await _save_result(ctx)
    except Exception as e:
        logger.warning(f"Failed to save result to storage: {e}")
        ctx.errors.append(f"postprocess/save: {e}")

    # Save content fingerprint for future similarity detection
    try:
        from src.core.content_fingerprint import save_fingerprint
        if ctx.content and ctx.content.text:
            save_fingerprint(
                text=ctx.content.text,
                content_hash=ctx.content.content_hash,
                title=ctx.content.title,
                source_url=ctx.content.source_url,
            )
    except Exception as e:
        logger.debug(f"Fingerprint save failed (non-blocking): {e}")

    # Run side effects (fire-and-forget, never blocks)
    try:
        from src.core.side_effects.base import SideEffectRunner
        from src.core.side_effects.notification import NotificationSideEffect
        from src.core.side_effects.stats_collector import StatsCollectorSideEffect

        # Build runner with default effects
        runner = SideEffectRunner([
            NotificationSideEffect(threshold=30.0),
            StatsCollectorSideEffect(),
        ])
        await runner.run_all(ctx)
    except Exception as e:
        logger.warning(f"Side effects failed (non-blocking): {e}")

    return ctx


# --- Helper functions ---


def _get_db_path(ctx: PipelineContext) -> str:
    """Get database path from context metadata or use default."""
    return ctx.metadata.get("db_path", "junk_detector.db")


async def _summarize_text(text: str, config) -> str:
    """Summarize long text using LLM.

    Uses the configured summarize_model (or primary_model as fallback).
    """
    import litellm

    model = config.summarize_model or config.primary_model
    max_chars = config.summarize_max_chars

    # Take first and last portions for context
    if len(text) > max_chars * 2:
        input_text = text[:max_chars] + "\n\n[...中间部分省略...]\n\n" + text[-2000:]
    else:
        input_text = text[:max_chars]

    prompt = (
        "请用中文对以下文章进行摘要，保留关键信息、论点和结论。"
        "摘要应保留原文的核心观点和重要细节，但控制在1500字以内。\n\n"
        f"文章内容：\n{input_text}"
    )

    kwargs: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
    }
    if config.api_base:
        kwargs["api_base"] = config.api_base

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content


async def _save_result(ctx: PipelineContext) -> None:
    """Save scoring result and embedding to storage."""
    from src.storage.db import save as db_save

    if ctx.result is None or ctx.content is None:
        return

    db_path = _get_db_path(ctx)
    db_save(ctx.result, ctx.content, db_path=db_path)

    # Also compute and store embedding for future similarity searches
    try:
        from src.core.embeddings import embed_content
        from src.storage.db import _get_connection, _ensure_initialized
        import json

        text = ctx.content.text
        embedding = await embed_content(
            text,
            model=ctx.config.embedding_model,
            api_base=ctx.config.embedding_api_base,
        )

        if embedding:
            _ensure_initialized(db_path)
            conn = _get_connection(db_path)
            try:
                conn.execute(
                    "UPDATE scores SET embedding_json = ? WHERE content_hash = ?",
                    (json.dumps(embedding), ctx.content.content_hash),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"Failed to save embedding: {e}")
