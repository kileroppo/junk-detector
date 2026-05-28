"""FastAPI application for junk-detector API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

# Auto-load .env (searches upward from cwd)
load_dotenv()

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
    yield


app = FastAPI(
    title="Junk Detector",
    description="AI content quality scorer — detect junk content with LLM-as-Judge + rules",
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware, config=RateLimitConfig())

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
from src.core.exceptions import ScoringError


@app.exception_handler(ScoringError)
async def scoring_error_handler(request, exc: ScoringError):
    """Return a styled error card for ScoringError."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content={"error": "scoring_failed", "detail": str(exc)},
    )

# ---------------------------------------------------------------------------
# Static files and Web UI
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).parent.parent / "web" / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(web_router)

app.include_router(preferences_router)

# Include authentication router
app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """Request body for the /score endpoint."""

    url: Optional[str] = Field(default=None, description="URL to fetch and score")
    text: Optional[str] = Field(default=None, max_length=50000, description="Raw text to score")
    title: Optional[str] = Field(default=None, description="Optional title for text input")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


import time

# Module-level cache for deep health check
_health_cache: dict = {"result": None, "timestamp": 0.0}
_HEALTH_CACHE_TTL = 60.0  # seconds


@app.get("/health")
async def health(deep: bool = False):
    """Health check endpoint.

    Args:
        deep: If True, attempts a minimal LLM API call to verify connectivity.
    """
    if not deep:
        return {"status": "ok"}

    # Check cache
    now = time.time()
    if _health_cache["result"] and (now - _health_cache["timestamp"]) < _HEALTH_CACHE_TTL:
        cached = _health_cache["result"]
        if cached.get("status") == "degraded":
            from fastapi.responses import JSONResponse

            return JSONResponse(content=cached, status_code=503)
        return cached

    # Deep check: minimal LLM request
    try:
        import litellm

        from src.core.config import get_model_config

        model_cfg = get_model_config()
        primary_model = model_cfg["primary"]

        start = time.time()
        await litellm.acompletion(
            model=primary_model,
            messages=[{"role": "user", "content": "respond ok"}],
            max_tokens=5,
            timeout=5.0,
        )
        latency_ms = int((time.time() - start) * 1000)

        result = {
            "status": "healthy",
            "llm_reachable": True,
            "model": primary_model,
            "latency_ms": latency_ms,
        }
        _health_cache["result"] = result
        _health_cache["timestamp"] = now
        return result

    except Exception as e:
        result = {
            "status": "degraded",
            "llm_reachable": False,
            "error": str(e)[:200],
        }
        _health_cache["result"] = result
        _health_cache["timestamp"] = now
        from fastapi.responses import JSONResponse

        return JSONResponse(content=result, status_code=503)


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
            detail="Either 'url' or 'text' must be provided",
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

    # Save to storage (user_id available if authenticated)
    try:
        save(result, content)
    except Exception:
        # Storage failure should not block returning the result
        pass

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
        results = query(filters=filters if filters else None, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {e}")

    return results
