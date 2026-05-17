"""FastAPI router for authentication endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.auth.dependencies import get_current_user
from src.auth.models import APIKeyInfo, Token, User, UserCreate, UserLogin
from src.auth.service import AuthService

logger = logging.getLogger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Default database path (same as the scoring database)
_DB_PATH = "junk_detector.db"


@router.post("/register", response_model=User)
async def register(user: UserCreate):
    """Register a new user.

    Returns the created user (without password).
    """
    try:
        created_user = AuthService.register(user, _DB_PATH)
        return created_user
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/login", response_model=Token)
async def login(creds: UserLogin):
    """Login and receive a JWT token.

    Returns an access token with expiration time.
    """
    try:
        token = AuthService.login(creds, _DB_PATH)
        return token
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user


@router.post("/regenerate-key", response_model=APIKeyInfo)
async def regenerate_key(current_user: User = Depends(get_current_user)):
    """Regenerate the API key for the current user.

    Returns the new API key information.
    """
    try:
        new_key = AuthService.regenerate_api_key(current_user.id, _DB_PATH)
        # Fetch updated user to get the created_at
        updated_user = AuthService.get_user_by_id(current_user.id, _DB_PATH)
        return APIKeyInfo(
            api_key=new_key,
            created_at=updated_user.created_at if updated_user else current_user.created_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
