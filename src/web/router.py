"""Web UI router — Jinja2 + HTMX dashboard routes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.responses import StreamingResponse

from src.core.config import get_model_config
from src.core.dimension_meta import DIMENSION_LABELS, NEGATIVE_DIMENSIONS, POSITIVE_DIMENSIONS
from src.storage.db import count_records, get_history, get_trends, query

# Template and static directories (relative to this file)
_BASE_DIR = Path(__file__).parent
_TEMPLATES_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"

router = APIRouter()
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

templates.env.globals["positive_dimensions"] = POSITIVE_DIMENSIONS
templates.env.globals["negative_dimensions"] = NEGATIVE_DIMENSIONS
templates.env.globals["dimension_labels"] = DIMENSION_LABELS

_FETCH_EXCEPTIONS = (ValueError, TimeoutError, RuntimeError)


def _fetch_error_template_context(exc: BaseException, url: str | None = None) -> dict:
    from src.web.extraction_errors import classify_fetch_error

    info = classify_fetch_error(exc, url=url)
    return {
        "fetch_error": info.to_dict(),
        "show_technical_detail": False,
    }


def _render_fetch_error_response(
    request: Request,
    exc: BaseException,
    url: str | None = None,
    *,
    is_htmx: bool = False,
    status_code: int = 422,
) -> HTMLResponse:
    ctx = _fetch_error_template_context(exc, url=url)
    if is_htmx:
        return templates.TemplateResponse(
            request,
            "partials/score_fetch_error.html",
            ctx,
            status_code=status_code,
        )
    return templates.TemplateResponse(
        request,
        "score_fetch_error_page.html",
        ctx,
        status_code=status_code,
    )


def _fetch_error_sse_payload(exc: BaseException, url: str | None = None) -> str:
    from src.web.extraction_errors import classify_fetch_error

    info = classify_fetch_error(exc, url=url)
    return json.dumps({"fetch_error": info.to_dict()}, ensure_ascii=False)


async def _resolve_score_content(
    input_type: Optional[str],
    text: Optional[str],
    url: Optional[str],
    title: Optional[str],
):
    """Resolve form input to Content; raises on missing input or fetch failure."""
    from src.extractors.text import extract_from_text
    from src.extractors.web import extract_from_url

    if input_type == "url" and url:
        return await extract_from_url(url)
    if text:
        if text.startswith(("http://", "https://")) and not url:
            return await extract_from_url(text)
        return extract_from_text(text, title=title)
    raise ValueError("请输入文本或 URL")


def _find_record(record_id: int) -> dict | None:
    """Load a single score record by id."""
    try:
        records = query(filters=None, limit=1000)
        return next((r for r in records if r.get("id") == record_id), None)
    except Exception:
        return None


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


@router.get("/playground", response_class=HTMLResponse)
async def playground(request: Request):
    """Interactive API playground page."""
    return templates.TemplateResponse(request, "playground.html")


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
    from src.core.scorer import score
    from src.storage.db import save

    is_htmx = request.headers.get("HX-Request") == "true"
    target_url = url or (
        text if text and text.startswith(("http://", "https://")) else None
    )

    try:
        content = await _resolve_score_content(input_type, text, url, title)
    except ValueError as e:
        if str(e) == "请输入文本或 URL":
            empty_ctx = {
                "fetch_error": {
                    "title": "缺少输入",
                    "reason": "请填写要评分的文本，或粘贴网页链接。",
                    "hints": ("在「URL」标签页粘贴链接，或在「文本」标签页粘贴正文。",),
                    "level": "error",
                    "detail": None,
                    "url": None,
                    "code": "empty_input",
                },
                "show_technical_detail": False,
            }
            if is_htmx:
                return templates.TemplateResponse(
                    request,
                    "partials/score_fetch_error.html",
                    empty_ctx,
                    status_code=422,
                )
            return templates.TemplateResponse(
                request,
                "score_fetch_error_page.html",
                empty_ctx,
                status_code=422,
            )
        return _render_fetch_error_response(
            request, e, target_url, is_htmx=is_htmx, status_code=422
        )
    except _FETCH_EXCEPTIONS as e:
        return _render_fetch_error_response(
            request, e, target_url, is_htmx=is_htmx, status_code=422
        )

    try:
        # Score with user-configured weights (+ optional feedback adjustments)
        from src.web.scoring_prefs import build_web_scoring_config

        scoring_config = build_web_scoring_config()
        result = await score(content.text, config=scoring_config)

        from src.core.scorer import attach_focus_guide

        if not content.content_hash:
            content.compute_hash()

        if result.focus_guide is None:
            attach_focus_guide(result, content.text)

        record_id = None
        content_hash = content.content_hash

        # Save to storage
        try:
            from src.storage.db import query_by_content_hash

            save(result, content)
            stored = query_by_content_hash(content.content_hash)
            if stored:
                record_id = stored.get("id")
        except Exception:
            pass

        from src.storage.db import prepare_content_for_storage

        stored_content, content_truncated = prepare_content_for_storage(content.text)

        from src.web.result_display import build_result_display_data

        result_data = build_result_display_data(
            overall_score=result.overall_score,
            dimensions=result.dimensions.model_dump(),
            labels=result.labels,
            summary=result.summary,
            model_used=result.model_used,
            cost=result.cost,
            confidence=result.confidence,
            scored_at=result.scored_at.isoformat(),
            title=content.title,
            source_url=content.source_url,
            focus_guide=result.focus_guide,
            content_text=stored_content,
            content_truncated=content_truncated,
            rule_hits=result.rule_hits,
            dimension_sources=result.dimension_sources,
            rule_score=result.rule_score,
            rules_fired=result.rules_fired,
            content_genre=result.content_genre,
        )

        # Source reputation warning
        source_warning = None
        if content.source_url:
            from urllib.parse import urlparse

            from src.core.source_reputation import check_auto_blacklist, is_blacklisted

            try:
                parsed = urlparse(content.source_url)
                domain = parsed.netloc or ""
                if domain.startswith("www."):
                    domain = domain[4:]

                if domain:
                    if is_blacklisted(domain):
                        source_warning = {
                            "level": "blacklisted",
                            "message": "来源已列入黑名单",
                        }
                    elif check_auto_blacklist(domain):
                        source_warning = {
                            "level": "low_reputation",
                            "message": "该来源历史评分较低",
                        }
            except Exception:
                pass

        result_data["source_warning"] = source_warning

        template_ctx = {
            "result": result_data,
            "record_id": record_id,
            "content_hash": content_hash,
        }

        if is_htmx:
            return templates.TemplateResponse(
                request,
                "partials/score_result_inline.html",
                template_ctx,
            )
        return templates.TemplateResponse(
            request,
            "result.html",
            template_ctx,
        )

    except Exception as e:
        from src.web.extraction_errors import FetchErrorInfo

        info = FetchErrorInfo(
            title="评分失败",
            reason="内容已获取，但 AI 分析过程出错。",
            hints=(
                "请稍后重试。",
                "若多次失败，请在设置中检查模型与 API Key 是否有效。",
            ),
            detail=str(e),
            code="scoring",
        )
        ctx = {"fetch_error": info.to_dict(), "show_technical_detail": False}
        if is_htmx:
            return templates.TemplateResponse(
                request,
                "partials/score_fetch_error.html",
                ctx,
                status_code=500,
            )
        return templates.TemplateResponse(
            request,
            "score_fetch_error_page.html",
            ctx,
            status_code=500,
        )


@router.get("/result/{record_id}", response_class=HTMLResponse)
async def result_detail(request: Request, record_id: int):
    """Show detailed scoring result for a specific record."""
    record = _find_record(record_id)

    if not record:
        return HTMLResponse(
            content="<h1>记录未找到</h1>",
            status_code=404,
        )

    from src.web.result_display import build_result_display_data_from_record

    result_data = build_result_display_data_from_record(record)

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "result": result_data,
            "record_id": record_id,
            "content_hash": record.get("content_hash"),
        },
    )


@router.get("/result/{record_id}/fragment", response_class=HTMLResponse)
async def result_fragment(request: Request, record_id: int):
    """Inline result HTML fragment for score-form streaming completion."""
    record = _find_record(record_id)

    if not record:
        return HTMLResponse(content="<div class=\"text-red-300\">记录未找到</div>", status_code=404)

    from src.web.result_display import build_result_display_data_from_record

    result_data = build_result_display_data_from_record(record)

    return templates.TemplateResponse(
        request,
        "result_fragment.html",
        {
            "result": result_data,
            "record_id": record_id,
            "content_hash": record.get("content_hash"),
        },
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
    import logging

    from src.core.rules import apply_rules
    from src.core.scorer import _calculate_overall, score
    from src.models.score import DimensionScores

    _sse_logger = logging.getLogger(__name__)

    async def event_generator():
        try:
            target_url = url or (
                text if text and text.startswith(("http://", "https://")) else None
            )
            try:
                content = await _resolve_score_content(input_type, text, url, title)
            except ValueError as e:
                if str(e) == "请输入文本或 URL":
                    payload = json.dumps(
                        {
                            "fetch_error": {
                                "title": "缺少输入",
                                "reason": "请填写要评分的文本，或粘贴网页链接。",
                                "hints": [
                                    "在「URL」标签页粘贴链接，或在「文本」标签页粘贴正文。",
                                ],
                                "level": "error",
                                "code": "empty_input",
                            }
                        },
                        ensure_ascii=False,
                    )
                else:
                    payload = _fetch_error_sse_payload(e, target_url)
                yield f"event: error\ndata: {payload}\n\n"
                return
            except _FETCH_EXCEPTIONS as e:
                payload = _fetch_error_sse_payload(e, target_url)
                yield f"event: error\ndata: {payload}\n\n"
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
            from src.web.scoring_prefs import build_web_scoring_config

            scoring_config = build_web_scoring_config()
            try:
                result = await asyncio.wait_for(
                    score(content.text, config=scoring_config),
                    timeout=60.0,
                )
            except asyncio.TimeoutError:
                _sse_logger.error("LLM scoring timed out after 60s")
                payload = json.dumps(
                    {
                        "fetch_error": {
                            "title": "分析超时",
                            "reason": "AI 评分用时过长，请稍后重试。",
                            "hints": ("可尝试缩短正文，或更换响应更快的模型。",),
                            "level": "error",
                            "code": "llm_timeout",
                        }
                    },
                    ensure_ascii=False,
                )
                yield f"event: error\ndata: {payload}\n\n"
                return

            record_id = None
            if not content.content_hash:
                content.compute_hash()

            from src.core.scorer import attach_focus_guide

            if result.focus_guide is None:
                attach_focus_guide(result, content.text)

            # Save to storage
            try:
                from src.storage.db import query_by_content_hash, save

                save(result, content)
                stored = query_by_content_hash(content.content_hash)
                if stored:
                    record_id = stored.get("id")
            except Exception:
                pass

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
                "record_id": record_id,
            }
            yield f"event: final_result\ndata: {json.dumps(final_data, ensure_ascii=False)}\n\n"

        except Exception:
            _sse_logger.exception("SSE score-stream error")
            payload = json.dumps(
                {
                    "fetch_error": {
                        "title": "评分失败",
                        "reason": "处理过程中出现意外错误，请稍后重试。",
                        "hints": ("若链接解析正常，请检查设置中的模型配置。",),
                        "level": "error",
                        "code": "internal",
                    }
                },
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {payload}\n\n"

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
):
    """Full history page with filters and pagination."""
    filters: dict = {}
    if min_score is not None and min_score > 0:
        filters["min_score"] = min_score
    if label:
        filters["label"] = label
    if date_from:
        filters["date_from"] = date_from

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
        error_html = f'<div class="bg-red-900 border border-red-700 rounded-lg p-4 text-red-300">对比评分失败: {str(e)}</div>'
        return HTMLResponse(content=error_html, status_code=500)


@router.get("/monitor-status", response_class=HTMLResponse)
async def monitor_status(request: Request):
    """Monitor status page (Thunder + Dispatcher stats)."""
    return templates.TemplateResponse(request, "monitor.html")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings: model API, platform cookies, appearance."""
    import json

    from src.core.model_presets import list_providers
    from src.core.user_settings import get_llm_settings_display
    from src.crawler_auth import list_all_platform_statuses
    from src.web.scoring_prefs import get_scoring_weight_dims

    llm = get_llm_settings_display()
    providers = list_providers()
    scoring_weight_dims = get_scoring_weight_dims()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "llm": llm,
            "llm_providers": providers,
            "llm_providers_json": json.dumps(providers, ensure_ascii=False),
            "platforms": list_all_platform_statuses(),
            "scoring_weight_dims": scoring_weight_dims,
            "weights_message": None,
        },
    )


@router.get("/cookies", response_class=HTMLResponse)
async def cookies_page_redirect():
    """Legacy route — cookies live under Settings."""
    return RedirectResponse(url="/settings#cookies", status_code=302)


@router.post("/api/settings/model", response_class=HTMLResponse)
async def api_settings_model(
    request: Request,
    provider: str = Form(...),
    model: str = Form(default=""),
    model_custom: str = Form(default=""),
    api_base: str = Form(default=""),
    api_key: str = Form(default=""),
):
    """Save LLM provider / model / base URL / API key."""
    from src.core.model_presets import LLM_PROVIDERS, get_provider
    from src.core.user_settings import get_llm_settings_display, save_llm_settings

    provider = provider.strip()
    if provider not in LLM_PROVIDERS:
        return HTMLResponse("Unknown provider", status_code=400)

    chosen_model = (model_custom if provider == "custom" else model).strip()
    if not chosen_model:
        chosen_model = get_provider(provider).get("default_model", "")

    save_llm_settings(
        provider=provider,
        model=chosen_model,
        api_base=api_base,
        api_key=api_key or None,
    )
    llm = get_llm_settings_display()
    response = templates.TemplateResponse(
        request,
        "partials/model_settings_status.html",
        {"llm": llm},
    )
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": "Model settings saved", "type": "success"}}
    )
    return response


def _render_scoring_weights_panel(request: Request, *, message: str | None = None):
    from src.web.scoring_prefs import get_scoring_weight_dims

    return templates.TemplateResponse(
        request,
        "partials/scoring_weights_form.html",
        {
            "scoring_weight_dims": get_scoring_weight_dims(),
            "weights_message": message,
        },
    )


@router.post("/api/settings/weights", response_class=HTMLResponse)
async def api_settings_weights(request: Request):
    """Save scoring dimension weights from settings sliders."""
    from src.web.scoring_prefs import parse_weight_form, save_scoring_weights

    form = await request.form()
    weights = parse_weight_form({k: str(v) for k, v in form.items()})
    if not weights:
        return HTMLResponse("No weights provided", status_code=400)
    save_scoring_weights(weights)
    response = _render_scoring_weights_panel(request, message="权重已保存，后续评分将使用新配置。")
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": "Scoring weights saved", "type": "success"}}
    )
    return response


@router.post("/api/settings/weights/reset", response_class=HTMLResponse)
async def api_settings_weights_reset(request: Request):
    """Reset scoring weights to config.yaml defaults."""
    from src.web.scoring_prefs import reset_scoring_weights

    reset_scoring_weights()
    response = _render_scoring_weights_panel(request, message="已恢复为 config.yaml 默认权重。")
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": "Weights reset to defaults", "type": "info"}}
    )
    return response


# ---------------------------------------------------------------------------
# Cookie management API (Web UI + programmatic)
# ---------------------------------------------------------------------------


def _cookie_platforms_context():
    from src.crawler_auth import list_all_platform_statuses

    return {"platforms": list_all_platform_statuses()}


def _single_platform_card(request: Request, platform_id: str):
    from src.crawler_auth import describe_platform
    from src.crawler_auth.cookie_store import CookieStore

    return templates.TemplateResponse(
        request,
        "partials/cookie_platforms.html",
        {"platforms": [describe_platform(CookieStore(), platform_id)]},
    )


@router.get("/api/cookies", response_class=JSONResponse)
async def api_cookies_list():
    """List cookie status for all registered platforms."""
    from src.crawler_auth import list_all_platform_statuses

    return JSONResponse(content=list_all_platform_statuses())


@router.post("/api/cookies/{platform_id}/import", response_class=HTMLResponse)
async def api_cookies_import(
    request: Request,
    platform_id: str,
    cookie_raw: str = Form(...),
    replace: Optional[str] = Form(default=None),
):
    """Import cookies for a platform from pasted text."""
    from src.crawler_auth import import_cookies

    try:
        result = import_cookies(
            platform_id,
            cookie_raw,
            merge=replace != "true",
        )
    except ValueError as exc:
        return HTMLResponse(
            content=(
                f'<div class="bg-red-900/50 border border-red-700 rounded-lg p-3 text-red-300 text-sm">'
                f"{exc}</div>"
            ),
            status_code=400,
        )

    keys = ", ".join(result["imported_keys"])
    response = _single_platform_card(request, platform_id)
    response.headers["HX-Trigger"] = json.dumps(
        {
            "showToast": {
                "message": f"Imported {len(result['imported_keys'])} keys: {keys}",
                "type": "success",
            }
        }
    )
    return response


@router.post("/api/cookies/{platform_id}/clear", response_class=HTMLResponse)
async def api_cookies_clear(request: Request, platform_id: str):
    """Clear stored cookies for a platform."""
    from src.crawler_auth import clear_platform_cookies

    try:
        clear_platform_cookies(platform_id)
    except ValueError as exc:
        return HTMLResponse(
            content=(
                f'<div class="bg-red-900/50 border border-red-700 rounded-lg p-3 text-red-300 text-sm">'
                f"{exc}</div>"
            ),
            status_code=400,
        )

    response = _single_platform_card(request, platform_id)
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": "Cookies cleared", "type": "info"}}
    )
    return response


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
        headers={"HX-Trigger": '{"showToast": {"message": "Monitor started", "type": "success"}}'},
    )


@router.post("/api/monitor/stop", response_class=HTMLResponse)
async def api_monitor_stop(request: Request):
    """Stop the Thunder monitor."""
    from src.core.monitor_service import MonitorService

    service = MonitorService()
    service.stop()
    return HTMLResponse(
        content="",
        headers={"HX-Trigger": '{"showToast": {"message": "Monitor stopped", "type": "info"}}'},
    )


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
                pass
            results.append({
                "url": url,
                "title": content.title or url,
                "overall_score": result.overall_score,
                "summary": result.summary,
                "success": True,
            })
        except Exception as e:
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
    from src.storage.db import save_feedback

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
    from src.storage.db import query as _query_records

    existing = _query_records(filters=None, limit=1000)
    record = next((r for r in existing if r.get("id") == score_id_int), None)
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
