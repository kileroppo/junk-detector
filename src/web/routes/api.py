"""API routes — JSON/HTMX API endpoints for junk-detector."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.storage.db import get_trends

logger = logging.getLogger(__name__)

# Template directory (relative to src/web/)
_BASE_DIR = Path(__file__).parent.parent
_TEMPLATES_DIR = _BASE_DIR / "templates"

router = APIRouter()
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Monitor API endpoints
# ---------------------------------------------------------------------------


@router.post("/api/monitor/start", response_class=HTMLResponse)
async def api_monitor_start(request: Request):
    """Start the Thunder monitor."""
    from src.core.monitor_service import MonitorService

    service = MonitorService()
    service.start()
    return HTMLResponse(
        content="",
        headers={"HX-Trigger": json.dumps({"showToast": {"message": "Monitor started", "type": "success"}, "refreshMonitorStats": ""})},
    )


@router.post("/api/monitor/stop", response_class=HTMLResponse)
async def api_monitor_stop(request: Request):
    """Stop the Thunder monitor."""
    from src.core.monitor_service import MonitorService

    service = MonitorService()
    service.stop()
    return HTMLResponse(
        content="",
        headers={"HX-Trigger": json.dumps({"showToast": {"message": "Monitor stopped", "type": "info"}, "refreshMonitorStats": ""})},
    )


@router.post("/api/monitor/feeds", response_class=HTMLResponse)
async def api_monitor_add_feed(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
):
    """Add a new RSS feed to the monitor."""
    # Validate URL starts with http:// or https://
    if not url.startswith(("http://", "https://")):
        return HTMLResponse(
            content='<div class="text-red-400">URL 必须以 http:// 或 https:// 开头</div>',
            status_code=422,
        )

    from src.core.monitor_service import MonitorService

    service = MonitorService()
    service.add_feed(name, url)
    return HTMLResponse(
        content="",
        headers={"HX-Trigger": json.dumps({"showToast": {"message": "\u4fe1\u6e90\u5df2\u6dfb\u52a0", "type": "success"}, "refreshMonitorStats": ""})},
    )


@router.delete("/api/monitor/feeds/{feed_index}", response_class=HTMLResponse)
async def api_monitor_delete_feed(request: Request, feed_index: int):
    """Remove an RSS feed from the monitor by index."""
    from src.core.monitor_service import MonitorService

    service = MonitorService()
    removed = service.remove_feed(feed_index)
    if not removed:
        return HTMLResponse(content="", status_code=404)
    return HTMLResponse(
        content="",
        headers={"HX-Trigger": json.dumps({"showToast": {"message": "\u4fe1\u6e90\u5df2\u5220\u9664", "type": "info"}, "refreshMonitorStats": ""})},
    )


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------


@router.post("/api/feedback")
async def api_feedback(request: Request):
    """Store user feedback (wrong/correct) for a scoring result.

    Auth note: This endpoint has no authentication by design. The application
    is intended for personal/single-user deployment (single-worker uvicorn).
    If multi-user deployment is needed in the future, add JWT auth middleware.
    """
    from fastapi.responses import JSONResponse

    from src.core.adaptive_weights import (
        compute_feedback_adjustments,
        save_weight_adjustment,
    )
    from src.storage.db import get_by_id, save_feedback

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON"}, status_code=400)

    score_id = body.get("score_id")
    verdict = body.get("verdict")

    if score_id is None or verdict not in ("wrong", "correct"):
        return JSONResponse(
            content={"error": "score_id and verdict (wrong/correct) required"},
            status_code=422,
        )

    # Validate that score_id references an existing record
    score_id_int = int(score_id)
    record = get_by_id(score_id_int)
    if record is None:
        return JSONResponse(
            content={"error": "score_id not found"},
            status_code=404,
        )

    save_feedback(
        score_id=score_id_int,
        content_hash=body.get("content_hash", ""),
        verdict=verdict,
    )

    # Compute and store adaptive weight adjustments
    overall_score = body.get("overall_score")
    dimensions = body.get("dimensions")
    user_id = body.get("user_id", "anonymous")

    if verdict == "wrong" and overall_score is not None and dimensions:
        adjustments = compute_feedback_adjustments(verdict, overall_score, dimensions)
        for dim, adj in adjustments.items():
            save_weight_adjustment(user_id=user_id, dimension=dim, adjustment=adj)

    return JSONResponse(content={"status": "ok"})


# ---------------------------------------------------------------------------
# Batch scoring endpoint
# ---------------------------------------------------------------------------


@router.post("/score-batch", response_class=HTMLResponse)
async def score_batch(
    request: Request,
    urls: str = Form(default=""),
):
    """Batch score multiple URLs (one per line).

    Accepts newline-separated URLs, validates each one, scores them
    sequentially, and returns results as a list of cards.
    """
    from src.core.scorer import score
    from src.extractors.web import extract_from_url
    from src.storage.db import save

    raw_urls = [u.strip() for u in urls.strip().splitlines() if u.strip()]

    if not raw_urls:
        return HTMLResponse(
            content='<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">请输入至少一个 URL</div>',
            status_code=422,
        )

    # Validate URLs
    valid_urls = []
    for u in raw_urls:
        if u.startswith(("http://", "https://")):
            valid_urls.append(u)

    if not valid_urls:
        return HTMLResponse(
            content='<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">未找到有效的 URL（需以 http:// 或 https:// 开头）</div>',
            status_code=422,
        )

    results = []
    for url in valid_urls:
        try:
            content = await extract_from_url(url)
            result = await score(content.text)
            try:
                save(result, content)
            except Exception:
                logger.exception("Failed to save batch result for %s", url)
            results.append({
                "url": url,
                "title": content.title or url,
                "overall_score": result.overall_score,
                "summary": result.summary,
                "success": True,
            })
        except Exception as e:
            logger.exception("Batch scoring failed for %s", url)
            results.append({
                "url": url,
                "title": url,
                "overall_score": 0,
                "summary": str(e),
                "success": False,
            })

    return templates.TemplateResponse(
        request,
        "partials/batch_results.html",
        {"results": results},
    )


# ---------------------------------------------------------------------------
# Trends API endpoint
# ---------------------------------------------------------------------------


@router.get("/api/trends")
async def api_trends(request: Request, days: int = 28):
    """Return daily score trend data as JSON for the last N days."""
    from fastapi.responses import JSONResponse

    trends = get_trends(days=days)
    return JSONResponse(content={"trends": trends})
