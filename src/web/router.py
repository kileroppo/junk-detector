"""Web UI router — Jinja2 + HTMX dashboard routes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.storage.db import get_history, query

# Template and static directories (relative to this file)
_BASE_DIR = Path(__file__).parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"

router = APIRouter()
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"stats": stats},
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
    from src.core.scorer import score
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

        # Score the content
        result = await score(content.text)

        # Save to storage
        try:
            save(result, content)
        except Exception:
            pass

        # Build result dict for template
        result_data = {
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
        error_html = f'<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">评分失败: {str(e)}</div>'
        return HTMLResponse(content=error_html, status_code=500)


@router.get("/result/{record_id}", response_class=HTMLResponse)
async def result_detail(request: Request, record_id: int):
    """Show detailed scoring result for a specific record."""
    try:
        records = query(filters=None, limit=1000)
        record = next((r for r in records if r.get("id") == record_id), None)
    except Exception:
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


@router.get("/history-page", response_class=HTMLResponse)
async def history_page(
    request: Request,
    page: int = 1,
    min_score: Optional[float] = None,
    label: Optional[str] = None,
    date_from: Optional[str] = None,
    sort: Optional[str] = None,
):
    """Full history page with filters and pagination."""
    filters: dict = {}
    if min_score is not None and min_score > 0:
        filters["min_score"] = min_score
    if label:
        filters["label"] = label
    if date_from:
        filters["date_from"] = date_from

    # Pagination: fetch one extra page worth to determine if there's a next page
    offset_limit = page * 20
    try:
        all_results = query(
            filters=filters if filters else None,
            limit=offset_limit,
        )
        # Slice for current page
        start_idx = (page - 1) * 20
        results = all_results[start_idx : start_idx + 20]
    except Exception:
        results = []

    filter_context = {
        "min_score": min_score,
        "label": label or "",
        "date_from": date_from or "",
    }

    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "results": results,
            "filters": filter_context,
            "page": page,
        },
    )


@router.get("/monitor-status", response_class=HTMLResponse)
async def monitor_status(request: Request):
    """Monitor status page (Thunder + Dispatcher stats)."""
    return templates.TemplateResponse(request, "monitor.html")


# ---------------------------------------------------------------------------
# HTMX partial endpoints (return HTML fragments)
# ---------------------------------------------------------------------------


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



