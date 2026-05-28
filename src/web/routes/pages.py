"""Page routes — full HTML responses for junk-detector web UI."""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import StreamingResponse

from src.core.config import get_model_config
from src.storage.db import count_records, get_history, get_trends, query
from src.web.routes.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _compute_stats(records: list[dict]) -> dict:
    """Compute summary statistics from a list of score records."""
    total = len(records)
    if total == 0:
        return {
            "total": 0,
            "avg_score": 0.0,
            "junk_count": 0,
            "high_quality_count": 0,
        }

    scores = [r["overall_score"] for r in records]
    return {
        "total": total,
        "avg_score": sum(scores) / total,
        "junk_count": sum(1 for s in scores if s < 40),
        "high_quality_count": sum(1 for s in scores if s > 75),
    }


# ---------------------------------------------------------------------------
# Page routes (full HTML responses)
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Root — redirect to dashboard."""
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard home page with summary cards and recent scores."""
    try:
        records = get_history(limit=100)
    except Exception:
        records = []

    stats = _compute_stats(records)

    # Get trend data for chart
    try:
        trends = get_trends(days=28)
    except Exception:
        trends = []

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"stats": stats, "trends": trends},
    )


@router.get("/score-form", response_class=HTMLResponse)
async def score_form(request: Request):
    """Score submission form page."""
    return templates.TemplateResponse(request, "score_form.html")


@router.post("/score-submit", response_class=HTMLResponse)
async def score_submit(
    request: Request,
    input_type: Optional[str] = Form(default="text"),
    text: Optional[str] = Form(default=None),
    url: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
):
    """Handle form submission — score content and show result.

    If the request comes from HTMX, return an inline result fragment.
    Otherwise, redirect to the result detail page.
    """
    from src.extractors.text import extract_from_text
    from src.extractors.web import extract_from_url
    from src.storage.db import save

    # Determine input
    try:
        if input_type == "url" and url:
            content = await extract_from_url(url)
        elif text:
            # If text looks like a URL, try extracting
            if text.startswith(("http://", "https://")) and not url:
                content = await extract_from_url(text)
            else:
                content = extract_from_text(text, title=title)
        else:
            # Return error
            return HTMLResponse(
                content='<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">请输入文本或 URL</div>',
                status_code=422,
            )

        # Score the content (with adaptive weights from user feedback)
        from src.core.adaptive_weights import get_adjusted_weights
        from src.core.scoring_service import score_with_full_report

        adjusted_weights = get_adjusted_weights(user_id="anonymous")
        # Build a ScoringConfig with adjusted weights if feedback has modified them
        scoring_config = None
        if adjusted_weights:
            try:
                from src.core.config import load_config as _load_scoring_cfg

                base_cfg = _load_scoring_cfg()
                # Only customize if adjustments differ from base
                if adjusted_weights != base_cfg.weights:
                    scoring_config = base_cfg.model_copy(deep=True)
                    scoring_config.weights = adjusted_weights
            except Exception:
                pass

        report = await score_with_full_report(
            content.text, source_url=content.source_url, config=scoring_config
        )

        # Save to storage
        try:
            save(report.result, content)
        except Exception:
            logger.exception("Failed to save scoring result")

        # Build result dict for template
        result_data = {
            "overall_score": report.result.overall_score,
            "dimensions": report.result.dimensions.model_dump(),
            "labels": report.result.labels,
            "summary": report.result.summary,
            "model_used": report.result.model_used,
            "cost": report.result.cost,
            "confidence": report.result.confidence,
            "scored_at": report.result.scored_at.isoformat()[:19],
            "title": content.title,
            "source_url": content.source_url,
            "focus_guide": report.focus_guide,
            "rule_hits": report.rule_hits,
            "dimension_sources": report.dimension_sources,
            "rule_score": report.rule_score,
            "llm_score": report.llm_score,
            "score_divergence": report.score_divergence,
            "divergence_warning": report.divergence_warning,
            "rules_fired": report.rules_fired,
            "source_warning": report.source_warning,
        }

        # Check if HTMX request
        is_htmx = request.headers.get("HX-Request") == "true"
        if is_htmx:
            # Return inline result fragment
            return templates.TemplateResponse(
                request,
                "result.html",
                {"result": result_data},
            )
        else:
            # For non-HTMX, try to find the saved record ID and redirect
            # Fall back to rendering result directly
            return templates.TemplateResponse(
                request,
                "result.html",
                {"result": result_data},
            )

    except Exception as e:
        logger.exception("score_submit failed")
        error_html = '<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">评分失败，请稍后重试</div>'
        return HTMLResponse(content=error_html, status_code=500)


@router.get("/result/{record_id}", response_class=HTMLResponse)
async def result_detail(request: Request, record_id: int):
    """Show detailed scoring result for a specific record."""
    from src.storage.db import get_by_id

    try:
        record = get_by_id(record_id)
    except Exception:
        logger.exception("result_detail lookup failed for id=%s", record_id)
        record = None

    if not record:
        return HTMLResponse(
            content="<h1>记录未找到</h1>",
            status_code=404,
        )

    # Build result_data from db record
    result_data = {
        "overall_score": record["overall_score"],
        "dimensions": record.get("dimensions", {}),
        "labels": record.get("labels", []),
        "summary": record.get("summary", ""),
        "model_used": record.get("model_used", ""),
        "cost": record.get("cost", 0),
        "confidence": record.get("confidence", 1.0),
        "scored_at": record.get("scored_at", "")[:19],
        "title": record.get("title"),
        "source_url": record.get("source_url"),
    }

    return templates.TemplateResponse(
        request,
        "result.html",
        {"result": result_data},
    )


@router.post("/score-stream")
async def score_stream(
    request: Request,
    input_type: Optional[str] = Form(default="text"),
    text: Optional[str] = Form(default=None),
    url: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
):
    """SSE streaming endpoint for progressive scoring.

    First event: immediate rule-engine results.
    Second event: full LLM scoring result.
    """
    import asyncio

    from src.core.rules import apply_rules
    from src.core.scorer import _calculate_overall, score
    from src.extractors.text import extract_from_text
    from src.extractors.web import extract_from_url
    from src.models.score import DimensionScores

    async def event_generator():
        try:
            # Determine input
            if input_type == "url" and url:
                content = await extract_from_url(url)
            elif text:
                if text.startswith(("http://", "https://")) and not url:
                    content = await extract_from_url(text)
                else:
                    content = extract_from_text(text, title=title)
            else:
                error_data = json.dumps({"error": "请输入文本或 URL"}, ensure_ascii=False)
                yield f"event: error\ndata: {error_data}\n\n"
                return

            # Step 1: immediate rule-engine results
            rule_result = apply_rules(content.text)

            # Build partial dimensions from rules
            positive_default = 50.0
            negative_default = 0.0
            dims_dict: dict[str, float] = {}
            for dim in ["originality", "info_density", "reasoning_quality", "readability", "timeliness"]:
                dims_dict[dim] = rule_result.dimension_overrides.get(dim, positive_default)
            for dim in ["ai_generated_prob", "emotional_manipulation", "advertorial_prob", "scam_prob"]:
                dims_dict[dim] = rule_result.dimension_overrides.get(dim, negative_default)

            dimensions = DimensionScores(**dims_dict)
            config = None
            try:
                from src.core.config import load_config
                config = load_config()
            except Exception:
                pass

            if config:
                overall = _calculate_overall(dimensions, config)
            else:
                overall = 50.0

            rules_data = {
                "type": "rules_result",
                "overall_score": overall,
                "dimensions": dims_dict,
                "matched_rules": rule_result.matched_rules,
                "title": content.title,
            }
            yield f"event: rules_result\ndata: {json.dumps(rules_data, ensure_ascii=False)}\n\n"

            # Step 2: full LLM scoring (with timeout to prevent indefinite blocking)
            try:
                result = await asyncio.wait_for(score(content.text), timeout=60.0)
            except asyncio.TimeoutError:
                logger.error("LLM scoring timed out after 60s")
                error_data = json.dumps({"error": "LLM 分析超时，请稍后重试"}, ensure_ascii=False)
                yield f"event: error\ndata: {error_data}\n\n"
                return

            # Save to storage
            try:
                from src.storage.db import save
                save(result, content)
            except Exception:
                logger.exception("Failed to save result during score-stream")

            final_data = {
                "type": "final_result",
                "overall_score": result.overall_score,
                "dimensions": result.dimensions.model_dump(),
                "labels": result.labels,
                "summary": result.summary,
                "model_used": result.model_used,
                "cost": result.cost,
                "confidence": result.confidence,
                "scored_at": result.scored_at.isoformat()[:19],
                "title": content.title,
                "source_url": content.source_url,
            }
            yield f"event: final_result\ndata: {json.dumps(final_data, ensure_ascii=False)}\n\n"

        except Exception:
            logger.exception("SSE score-stream error")
            error_data = json.dumps({"error": "评分过程出错，请稍后重试"}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/history-page", response_class=HTMLResponse)
async def history_page(
    request: Request,
    page: int = 1,
    min_score: Optional[float] = None,
    label: Optional[str] = None,
    date_from: Optional[str] = None,
    sort: Optional[str] = None,
    search: Optional[str] = None,
):
    """Full history page with filters and pagination."""
    filters: dict = {}
    if min_score is not None and min_score > 0:
        filters["min_score"] = min_score
    if label:
        filters["label"] = label
    if date_from:
        filters["date_from"] = date_from
    if search:
        filters["search"] = search

    per_page = 20
    offset = (page - 1) * per_page

    try:
        total = count_records(filters=filters if filters else None)
        results = query(
            filters=filters if filters else None,
            limit=per_page,
            offset=offset,
        )
    except Exception:
        results = []
        total = 0

    filter_context = {
        "min_score": min_score,
        "label": label or "",
        "date_from": date_from or "",
        "search": search or "",
    }

    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "results": results,
            "filters": filter_context,
            "page": page,
            "total": total,
            "per_page": per_page,
        },
    )


@router.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request):
    """Comparison mode page with two side-by-side inputs."""
    return templates.TemplateResponse(request, "compare.html")


@router.post("/compare-submit", response_class=HTMLResponse)
async def compare_submit(
    request: Request,
    text_a: Optional[str] = Form(default=None),
    text_b: Optional[str] = Form(default=None),
):
    """Score two texts and return side-by-side comparison results."""
    from src.core.scorer import score

    if not text_a or not text_b:
        return HTMLResponse(
            content='<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">请输入两段文本进行对比</div>',
            status_code=422,
        )

    try:
        result_a = await score(text_a)
        result_b = await score(text_b)

        result_data_a = {
            "overall_score": result_a.overall_score,
            "dimensions": result_a.dimensions.model_dump(),
            "labels": result_a.labels,
            "summary": result_a.summary,
        }
        result_data_b = {
            "overall_score": result_b.overall_score,
            "dimensions": result_b.dimensions.model_dump(),
            "labels": result_b.labels,
            "summary": result_b.summary,
        }

        return templates.TemplateResponse(
            request,
            "partials/compare_result.html",
            {"result_a": result_data_a, "result_b": result_data_b},
        )

    except Exception as e:
        logger.exception("compare_submit failed")
        error_html = '<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">对比评分失败，请稍后重试</div>'
        return HTMLResponse(content=error_html, status_code=500)


@router.get("/monitor-status", response_class=HTMLResponse)
async def monitor_status(request: Request):
    """Monitor status page (Thunder + Dispatcher stats)."""
    return templates.TemplateResponse(request, "monitor.html")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page with model config, scoring preferences, and theme."""
    api_key_configured = bool(os.environ.get("DEEPSEEK_API_KEY"))
    try:
        model_cfg = get_model_config()
        model_name = model_cfg.get("primary", "deepseek/deepseek-chat")
    except Exception:
        model_name = "deepseek/deepseek-chat"
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"api_key_configured": api_key_configured, "model_name": model_name},
    )
