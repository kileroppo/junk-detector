"""Pydantic models for authentication."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Request model for user registration."""

    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6)
    email: str | None = None


class UserLogin(BaseModel):
    """Request model for user login."""

    username: str
    password: str


class User(BaseModel):
    """User representation (never includes password)."""

    id: int
    username: str
    email: str | None = None
    api_key: str
    created_at: datetime
    is_active: bool = True


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class APIKeyInfo(BaseModel):
    """API key information response."""

    api_key: str
    created_at: datetime
