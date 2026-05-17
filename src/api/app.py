"""FastAPI application for junk-detector API."""

from __future__ import annotations

from typing import Optional

from dotenv import load_dotenv

# Auto-load .env (searches upward from cwd)
load_dotenv()

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

app = FastAPI(
    title="Junk Detector",
    description="AI content quality scorer — detect junk content with LLM-as-Judge + rules",
    version="0.1.0",
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


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ScoreRequest(BaseModel):
    """Request body for the /score endpoint."""

    url: Optional[str] = Field(default=None, description="URL to fetch and score")
    text: Optional[str] = Field(default=None, description="Raw text to score")
    title: Optional[str] = Field(default=None, description="Optional title for text input")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


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
    result = await score(content.text)

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
