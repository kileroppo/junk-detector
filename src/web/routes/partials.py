"""HTMX partial routes — return HTML fragments for dynamic updates."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.storage.db import get_history
from src.web.routes.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/partials/recent-scores", response_class=HTMLResponse)
async def partials_recent_scores(request: Request):
    """Return last 10 scores as HTML table rows (for HTMX polling)."""
    try:
        scores = get_history(limit=10)
    except Exception:
        scores = []

    return templates.TemplateResponse(
        request,
        "partials/recent_scores.html",
        {"scores": scores},
    )


@router.get("/partials/toast", response_class=HTMLResponse)
async def partials_toast(
    request: Request,
    message: str = "操作完成",
    type: str = "info",
):
    """Return a toast notification fragment for HTMX."""
    valid_types = ("success", "error", "info")
    if type not in valid_types:
        type = "info"
    return templates.TemplateResponse(
        request,
        "partials/toast.html",
        {"message": message, "type": type},
    )


@router.get("/partials/monitor-stats", response_class=HTMLResponse)
async def partials_monitor_stats(request: Request):
    """Return monitor stats fragment for HTMX polling."""
    from src.core.monitor_service import MonitorService

    service = MonitorService()
    stats = service.get_stats()
    return templates.TemplateResponse(
        request,
        "partials/monitor_stats.html",
        {
            "thunder": stats["thunder"],
            "dispatcher": stats["dispatcher"],
            "is_running": service.is_running,
            "recent_items": stats.get("recent_items", []),
            "feeds": stats.get("feeds", []),
            "last_fetch_time": stats.get("last_fetch_time"),
        },
    )


@router.get("/partials/roi-stats", response_class=HTMLResponse)
async def partials_roi_stats(request: Request):
    """Return Token ROI stats card fragment for HTMX polling."""
    from src.core.token_roi import get_roi_stats

    stats = get_roi_stats()
    return templates.TemplateResponse(
        request,
        "partials/roi_stats.html",
        {"stats": stats},
    )
