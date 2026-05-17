"""FastAPI application for junk-detector API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Auto-load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.core.scorer import score
from src.extractors.text import extract_from_text
from src.extractors.web import extract_from_url
from src.models.score import ScoreResult
from src.storage.db import query, save

app = FastAPI(
    title="Junk Detector",
    description="AI content quality scorer — detect junk content with LLM-as-Judge + rules",
    version="0.1.0",
)


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
async def score_content(request: ScoreRequest):
    """Score content for quality.

    Accepts either a URL (fetches and extracts content) or raw text.
    Applies rules + LLM judge, computes overall score and labels,
    saves to storage, and returns the full ScoreResult.
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

    # Save to storage
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
):
    """Get scoring history with optional filters.

    Query params:
        limit: Maximum records to return (default 20).
        min_score: Filter by minimum overall_score.
        label: Filter by label substring match.
        date_from: Filter by scored_at >= date (ISO format).
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
