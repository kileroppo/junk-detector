"""FastAPI router for user preferences endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.preferences.models import (
    MonitoredSource,
    PreferencesUpdate,
    UserPreferences,
)
from src.preferences.service import PreferencesService

logger = logging.getLogger("preferences")

# ---------------------------------------------------------------------------
# Auth dependency — graceful fallback if auth module not ready
# ---------------------------------------------------------------------------

try:
    from src.auth.dependencies import get_current_user
    from src.auth.models import User
except ImportError:
    logger.warning(
        "Auth module not available, using mock user fallback (user_id=0)"
    )
    from src.auth.models import User  # type: ignore[no-redef]

    from datetime import datetime

    async def get_current_user() -> User:  # type: ignore[misc]
        """Fallback: return a mock user when auth module is not ready."""
        return User(
            id=0,
            username="anonymous",
            api_key="mock-key",
            created_at=datetime.now(),
            is_active=True,
        )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=UserPreferences)
async def get_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get current user's preferences."""
    return PreferencesService.get_preferences(current_user.id)


@router.put("", response_model=UserPreferences)
async def replace_preferences(
    prefs: UserPreferences,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Replace all preferences for the current user."""
    # Ensure user_id matches the authenticated user
    prefs.user_id = current_user.id
    return PreferencesService.save_preferences(prefs)


@router.patch("", response_model=UserPreferences)
async def update_preferences(
    update: PreferencesUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Partial update — only provided fields are changed."""
    return PreferencesService.update_preferences(current_user.id, update)


@router.delete("")
async def delete_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Reset preferences to defaults."""
    PreferencesService.delete_preferences(current_user.id)
    return {"detail": "Preferences reset to defaults"}


@router.get("/sources", response_model=list[MonitoredSource])
async def list_sources(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List user's monitored sources."""
    prefs = PreferencesService.get_preferences(current_user.id)
    return prefs.monitored_sources


@router.post("/sources", response_model=MonitoredSource, status_code=201)
async def add_source(
    source: MonitoredSource,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Add a new monitored source."""
    prefs = PreferencesService.get_preferences(current_user.id)

    # Check for duplicate name
    existing_names = {s.name for s in prefs.monitored_sources}
    if source.name in existing_names:
        raise HTTPException(
            status_code=409,
            detail=f"Source with name '{source.name}' already exists",
        )

    prefs.monitored_sources.append(source)
    PreferencesService.save_preferences(prefs)
    return source


@router.delete("/sources/{source_name}")
async def remove_source(
    source_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Remove a monitored source by name."""
    prefs = PreferencesService.get_preferences(current_user.id)

    original_count = len(prefs.monitored_sources)
    prefs.monitored_sources = [
        s for s in prefs.monitored_sources if s.name != source_name
    ]

    if len(prefs.monitored_sources) == original_count:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{source_name}' not found",
        )

    PreferencesService.save_preferences(prefs)
    return {"detail": f"Source '{source_name}' removed"}
