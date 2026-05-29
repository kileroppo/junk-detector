"""FastAPI application for junk-detector API."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

# Auto-load .env (searches upward from cwd)
load_dotenv()

from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api.notifications import NotificationDispatcher
from src.api.rate_limit import RateLimitConfig, RateLimitMiddleware
from src.auth.dependencies import get_optional_user
from src.auth.models import User
from src.auth.router import router as auth_router
from src.core.scorer import score
from src.extractors.text import extract_from_text
from src.extractors.web import extract_from_url
from src.models.score import ScoreResult
from src.preferences.router import router as preferences_router
from src.storage.db import query, save
from src.web import web_router

# Load notification config from config.yaml
_notification_config = {}
try:
    _config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if _config_path.exists():
        with open(_config_path) as f:
            _full_config = yaml.safe_load(f)
            _notification_config = _full_config.get("notification", {})
except Exception:
    pass

dispatcher = NotificationDispatcher(_notification_config)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup validation: ensure LLM API keys are configured."""
    from src.core.config import get_model_config

    has_key = any(
        os.environ.get(k) for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
    )
    if not has_key:
        model_cfg = get_model_config()
        primary_model = model_cfg.get("primary", "")
        if not primary_model.startswith("ollama"):
            raise RuntimeError(
                "No LLM API key configured. Set one of: "
                "DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY"
            )
    app.state.startup_time = time.time()
    app.state.score_count = 0
    yield
    # Shutdown: close shared HTTP client
    from src.extractors.http_pool import close_client
    await close_client()


app = FastAPI(
    title="Junk Detector",
    description="AI content quality scorer — detect junk content with LLM-as-Judge + rules",
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware, config=RateLimitConfig())

# ---------------------------------------------------------------------------
# Static files and Web UI
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).parent.parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(web_router)

app.include_router(preferences_router)

# Include authentication router
app.include_router(auth_router)

# Include WebSocket router
from src.api.websocket import router as ws_router

app.include_router(ws_router)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """Request body for the /score endpoint."""

    url: Optional[str] = Field(
        default=None,
        description="URL to fetch and score",
        json_schema_extra={"examples": ["https://mp.weixin.qq.com/s/example"]},
    )
    text: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="Raw text to score",
        json_schema_extra={"examples": ["日入过万 限时免费 加微信领取"]},
    )
    title: Optional[str] = Field(default=None, description="Optional title for text input")


class BatchScoreRequest(BaseModel):
    """Request body for /score/batch endpoint."""

    items: list[ScoreRequest] = Field(
        ..., min_length=1, max_length=50, description="List of items to score"
    )


class BatchScoreResponse(BaseModel):
    """Response for /score/batch endpoint."""

    results: list = Field(..., description="Scoring results in same order as input")
    total: int = Field(..., description="Total items processed")
    errors: int = Field(default=0, description="Number of items that failed")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health(deep: bool = False):
    """Health check endpoint.

    Args:
        deep: If True, attempts a minimal LLM API call to verify connectivity.
    """
    from src.core.rules import _ADVERTORIAL_KEYWORDS, _ANXIETY_PHRASES, _SCAM_KEYWORDS

    uptime = time.time() - getattr(app.state, "startup_time", time.time())
    rules_count = len(_SCAM_KEYWORDS) + len(_ANXIETY_PHRASES) + len(_ADVERTORIAL_KEYWORDS)

    base = {
        "status": "ok",
        "name": "\u9274\u771f",
        "version": "0.2.0",
        "uptime_seconds": round(uptime),
        "total_scores": getattr(app.state, "score_count", 0),
        "rules_loaded": rules_count,
    }

    if not deep:
        return base

    # Deep health check: ping the LLM API
    try:
        import litellm

        from src.core.config import get_model_config

        model_cfg = get_model_config()
        primary_model = model_cfg["primary"]

        await litellm.acompletion(
            model=primary_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            timeout=5.0,
        )
        base["llm_status"] = "connected"
        return base
    except Exception as e:
        logger.error("Deep health check failed: %s", e)
        base["status"] = "degraded"
        base["llm_status"] = "unreachable"
        return base


@app.get("/usage")
async def usage():
    """Return API usage stats for the current period."""
    from datetime import datetime, timedelta, timezone

    used = getattr(app.state, "score_count", 0)
    now = datetime.now(timezone.utc)
    # Resets at next midnight UTC
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "used": used,
        "limit": 30,
        "resets_at": tomorrow.isoformat(),
        "tier": "free",
    }


@app.get("/demo")
async def demo_score(text: Optional[str] = None):
    """Demo endpoint - scores text using rules-only without authentication.

    Try-before-buy for API evaluation. If `text` query parameter is provided,
    scores that text with the rules engine. Otherwise uses a default sample.

    Examples:
        GET /demo
        GET /demo?text=日入过万加微信领取
    """
    default_sample = (
        "想要财富自由吗？加入我们的区块链投资群，日入过万不是梦！"
        "限时免费名额，加微信领取。"
    )
    sample_text = text or default_sample

    from src.core.rules import apply_rules, should_skip_llm

    rule_result = apply_rules(sample_text)
    skip_llm, reason = should_skip_llm(rule_result, sample_text)

    # Determine verdict based on rule confidence
    junk_dims = ["scam_prob", "advertorial_prob", "emotional_manipulation"]
    max_junk = max(
        (rule_result.dimension_overrides.get(d, 0.0) for d in junk_dims), default=0.0
    )
    if max_junk >= 70:
        verdict = "junk"
    elif max_junk >= 40:
        verdict = "suspicious"
    else:
        verdict = "quality"

    # Compute overall score (inverted: high junk = low score)
    overall_score = max(0, 100 - max_junk)

    # Generate explanation using the explainer
    from src.core.explainer import explain_result
    from src.models.score import DimensionScores, ScoreResult

    mock_score = ScoreResult(
        overall_score=overall_score,
        dimensions=DimensionScores(
            originality=50, info_density=50, reasoning_quality=50,
            readability=50, timeliness=50, ai_generated_prob=0,
            emotional_manipulation=rule_result.dimension_overrides.get("emotional_manipulation", 0),
            advertorial_prob=rule_result.dimension_overrides.get("advertorial_prob", 0),
            scam_prob=rule_result.dimension_overrides.get("scam_prob", 0),
        ),
        labels=[], summary="demo", confidence=0.0, model_used="rules-only", cost=0.0,
    )
    explanation = explain_result(mock_score, rule_result, content=sample_text)

    # Build structured evidence from matched rules cross-referenced with content
    from src.core.rules import _ADVERTORIAL_KEYWORDS, _ANXIETY_PHRASES, _SCAM_KEYWORDS

    _RULE_KEYWORD_MAP = {
        "scam_keywords": (_SCAM_KEYWORDS, "诈骗/收割信号"),
        "advertorial_promo": (_ADVERTORIAL_KEYWORDS, "商业推广信号"),
        "emotional_anxiety_phrases": (_ANXIETY_PHRASES, "情绪操纵信号"),
        "emotional_anxiety_and_punctuation": (_ANXIETY_PHRASES, "情绪操纵信号"),
    }

    evidence_items: list[dict] = []
    paragraphs = [p for p in sample_text.split("。") if p.strip()]
    for rule_name in rule_result.matched_rules:
        if rule_name not in _RULE_KEYWORD_MAP:
            continue
        keywords, concern = _RULE_KEYWORD_MAP[rule_name]
        for para_idx, para in enumerate(paragraphs):
            for kw in keywords:
                if kw in para:
                    evidence_items.append({
                        "phrase": kw,
                        "location": f"第{para_idx + 1}段",
                        "concern": concern,
                    })

    # Actionable recommendation based on verdict
    recommendations = {
        "junk": "建议：不要点击文中链接，不要添加对方微信，不要转发",
        "suspicious": "建议：谨慎对待文中推荐，建议交叉验证信息来源",
        "quality": "建议：内容质量正常，可正常阅读",
    }
    recommendation = recommendations.get(verdict, "")

    is_custom = text is not None
    note = (
        "使用您提供的文本进行规则引擎评分（零成本，毫秒级响应）。"
        if is_custom
        else "这是默认样本的评分结果。传入 ?text=你的内容 来测试自己的文本。"
    )

    # Determine severity tier based on risk dimensions
    scam_prob = rule_result.dimension_overrides.get("scam_prob", 0)
    advertorial_prob = rule_result.dimension_overrides.get("advertorial_prob", 0)
    emotional_manipulation_score = rule_result.dimension_overrides.get("emotional_manipulation", 0)

    if scam_prob >= 60:
        severity = "danger"
    elif advertorial_prob >= 60 or emotional_manipulation_score >= 60:
        severity = "warning"
    elif max_junk > 0:
        severity = "info"
    else:
        severity = "safe"

    return {
        "overall_score": overall_score,
        "explanation": explanation,
        "evidence": evidence_items,
        "recommendation": recommendation,
        "verdict": verdict,
        "severity": severity,
        "dimensions": rule_result.dimension_overrides,
        "text_scored": sample_text,
        "is_custom_text": is_custom,
        "note": note,
    }


@app.post("/score", response_model=ScoreResult)
async def score_content(
    request: ScoreRequest,
    current_user: User | None = Depends(get_optional_user),
):
    """Score content for quality.

    Accepts either a URL (fetches and extracts content) or raw text.
    Applies rules + LLM judge, computes overall score and labels,
    saves to storage, and returns the full ScoreResult.

    Optionally accepts authentication — authenticated users get their
    scores associated with their user_id.
    """
    # Validate: must provide url or text (not both empty)
    if not request.url and not request.text:
        raise HTTPException(
            status_code=422,
            detail="请提供 'url' 或 'text' 参数",
        )

    # Dedup check — the scorer's own 7-day cache handles deduplication.
    # We still record in the TTL cache to track recent submissions,
    # but we always proceed to scoring (the scorer returns cached results if available).
    from src.core.dedup import should_score as should_score_content

    content_key = request.url or request.text or ""
    should_score_content(content_key)  # record in TTL cache for stats

    # Extract content
    try:
        if request.url:
            content = await extract_from_url(request.url)
        else:
            content = extract_from_text(request.text, title=request.title)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))

    # Score the content
    # Apply user preferences if authenticated
    user_config = None
    language = "zh"
    if current_user is not None:
        from src.preferences.service import PreferencesService

        user_config = PreferencesService.build_scoring_config(current_user.id)
        # Get language preference from user's preferences
        user_prefs = PreferencesService.get_preferences(current_user.id)
        language = user_prefs.language or "zh"

    if user_config is not None:
        result = await score(
            content.text, config=user_config, source_url=request.url, language=language
        )
    else:
        result = await score(content.text, source_url=request.url)

    # Increment score counter
    app.state.score_count = getattr(app.state, "score_count", 0) + 1

    # Save to storage (user_id available if authenticated)
    try:
        save(result, content, user_id=current_user.id if current_user is not None else None)
    except Exception:
        # Storage failure should not block returning the result
        pass

    # Notify via WebSocket (scoped to user, skip for anonymous)
    try:
        if current_user is not None:
            from src.api.websocket import manager as ws_manager
            await ws_manager.send_to_user(current_user.id, "score_completed", result.model_dump())
        # Anonymous scoring: no WebSocket notification (no targeted audience)
    except Exception:
        pass  # Notification failure should never block scoring response

    # Webhook alert for high-risk content (score < 40) - only for authenticated users
    # to prevent anonymous flood attacks
    try:
        if result.overall_score < 40 and current_user is not None:
            await dispatcher.send_webhook(result.model_dump())
    except Exception:
        pass  # Webhook failure should never block scoring response

    return result


@app.get("/history")
async def get_history(
    limit: int = 20,
    min_score: Optional[float] = None,
    label: Optional[str] = None,
    date_from: Optional[str] = None,
    current_user: User | None = Depends(get_optional_user),
):
    """Get scoring history with optional filters.

    Query params:
        limit: Maximum records to return (default 20).
        min_score: Filter by minimum overall_score.
        label: Filter by label substring match.
        date_from: Filter by scored_at >= date (ISO format).

    Optionally accepts authentication — authenticated users could
    get personalized history in the future.
    """
    filters: dict = {}
    if min_score is not None:
        filters["min_score"] = min_score
    if label is not None:
        filters["label"] = label
    if date_from is not None:
        filters["date_from"] = date_from

    try:
        results = query(
            filters=filters if filters else None,
            limit=limit,
            user_id=current_user.id if current_user is not None else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")

    return results


@app.post("/score/batch", response_model=None)
async def score_batch(
    request: BatchScoreRequest,
    current_user: User | None = Depends(get_optional_user),
):
    """Score multiple items concurrently.

    Accepts a list of items (text or URL), scores them with
    max 5 concurrent operations, and broadcasts each result via WebSocket.
    """
    import asyncio

    semaphore = asyncio.Semaphore(5)
    user_id = current_user.id if current_user is not None else None

    async def score_single(item: ScoreRequest, index: int) -> ScoreResult | dict:
        async with semaphore:
            try:
                if not item.url and not item.text:
                    return {"error": "请提供 'url' 或 'text' 参数", "index": index}

                # Extract content
                if item.url:
                    content = await extract_from_url(item.url)
                else:
                    content = extract_from_text(item.text, title=item.title)

                # Score
                result = await score(content.text, source_url=item.url)

                # Save
                try:
                    save(result, content, user_id=user_id)
                except Exception:
                    pass

                # Notify per-item completion (scoped to user, skip for anonymous)
                try:
                    if user_id is not None:
                        from src.api.websocket import manager as ws_manager
                        await ws_manager.send_to_user(user_id, "score_completed", result.model_dump())
                    # Anonymous scoring: no WebSocket notification (no targeted audience)
                except Exception:
                    pass

                return result
            except Exception as e:
                return {"error": str(e), "index": index}

    tasks = [score_single(item, i) for i, item in enumerate(request.items)]
    results = await asyncio.gather(*tasks)

    errors = sum(1 for r in results if isinstance(r, dict) and "error" in r)

    return BatchScoreResponse(
        results=list(results),
        total=len(results),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# SSE Streaming Endpoint
# ---------------------------------------------------------------------------


@app.post("/score/stream")
async def score_stream(
    request: ScoreRequest,
    accept: str = Header(default="application/json"),
    current_user: User | None = Depends(get_optional_user),
):
    """Score content with Server-Sent Events streaming.

    Sends rules result immediately, then streams LLM dimensions as they complete.
    Use Accept: text/event-stream header to enable streaming.
    Unauthenticated users get rules-only results (no LLM cost incurred).
    """
    if "text/event-stream" not in accept:
        # Fall back to normal scoring
        return await score_content(request, current_user=current_user)

    async def event_generator():
        from src.core.rules import apply_rules, should_skip_llm
        from src.extractors.text import extract_from_text as _extract_text

        # Extract content
        text_content = request.text
        if request.url:
            from src.extractors.web import extract_from_url as _extract_url

            content = await _extract_url(request.url)
            text_content = content.text

        # Phase 1: Rules result (instant)
        rule_result = apply_rules(text_content)
        rules_data = {
            "phase": "rules",
            "matched_rules": rule_result.matched_rules,
            "dimension_overrides": rule_result.dimension_overrides,
            "confidence": rule_result.confidence,
        }
        yield f"event: rules_result\ndata: {json.dumps(rules_data, ensure_ascii=False)}\n\n"

        # Phase 2: Full scoring (only for authenticated users to prevent LLM cost abuse)
        skip, reason = should_skip_llm(rule_result, text_content)
        if not skip and current_user is not None:
            from src.core.scorer import score as do_score

            result = await do_score(text_content)
            yield f"event: complete\ndata: {json.dumps(result.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        else:
            # Rules-only result (either rules are confident, or user is unauthenticated)
            yield f"event: complete\ndata: {json.dumps({'rules_only': True, 'overrides': rule_result.dimension_overrides}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Batch File Upload Endpoint
# ---------------------------------------------------------------------------

# In-memory job store
_batch_jobs: dict[str, dict] = {}
_BATCH_JOB_TTL_SECONDS = 3600  # 1 hour TTL for batch jobs


def _evict_expired_batch_jobs() -> None:
    """Remove batch jobs older than TTL."""
    now = time.time()
    expired_keys = [
        k for k, v in _batch_jobs.items()
        if now - v.get("created_at", now) > _BATCH_JOB_TTL_SECONDS
    ]
    for k in expired_keys:
        del _batch_jobs[k]


@app.post("/score/batch-upload")
async def score_batch_upload(file: UploadFile = File(...)):
    """Upload a CSV or JSONL file for batch scoring.

    CSV format: must have 'url' or 'text' column header.
    JSONL format: each line is {"url": "..."} or {"text": "..."}.

    Returns a job_id for polling results.
    """
    import asyncio
    import csv
    import io

    content_bytes = await file.read()
    content_str = content_bytes.decode("utf-8")

    items: list[dict] = []
    filename = file.filename or ""

    if filename.endswith(".jsonl") or filename.endswith(".json"):
        for line in content_str.strip().split("\n"):
            if line.strip():
                items.append(json.loads(line.strip()))
    else:
        # Assume CSV
        reader = csv.DictReader(io.StringIO(content_str))
        for row in reader:
            item: dict = {}
            if "url" in row:
                item["url"] = row["url"]
            elif "text" in row:
                item["text"] = row["text"]
            if item:
                items.append(item)

    if not items:
        raise HTTPException(status_code=400, detail="No valid items found in file")

    job_id = str(uuid.uuid4())[:8]
    _batch_jobs[job_id] = {"status": "processing", "total": len(items), "completed": 0, "results": [], "created_at": time.time()}

    # Process in background
    asyncio.create_task(_process_batch_job(job_id, items))

    return {"job_id": job_id, "total_items": len(items), "status": "processing"}


@app.get("/score/batch-upload/{job_id}")
async def get_batch_job(job_id: str):
    """Poll batch job status and results."""
    _evict_expired_batch_jobs()
    if job_id not in _batch_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _batch_jobs[job_id]


async def _process_batch_job(job_id: str, items: list[dict]):
    """Process batch items asynchronously."""
    for item in items:
        try:
            text = item.get("text", "")
            url = item.get("url", "")
            if url:
                from src.extractors.web import extract_from_url as _extract_url

                content = await _extract_url(url)
                text = content.text
            if text:
                result = await score(text)
                _batch_jobs[job_id]["results"].append(result.model_dump(mode="json"))
            else:
                _batch_jobs[job_id]["results"].append({"error": "No text or url provided"})
        except Exception as e:
            _batch_jobs[job_id]["results"].append({"error": str(e)})
        _batch_jobs[job_id]["completed"] += 1
    _batch_jobs[job_id]["status"] = "completed"
