"""FastAPI dependency functions for authentication."""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from src.auth.models import User
from src.auth.service import AuthService

logger = logging.getLogger("auth")

# Default database path (same as the scoring database)
_DB_PATH = "junk_detector.db"


def get_current_user(request: Request) -> User:
    """Extract and validate user credentials from the request.

    Checks in order:
    1. Authorization: Bearer <token> header
    2. X-API-Key header
    3. api_key query parameter

    Raises:
        HTTPException: 401 if no valid credentials found.

    Returns:
        Authenticated User object.
    """
    user = _extract_user(request)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(request: Request) -> User | None:
    """Extract user credentials if present, but don't require them.

    Same logic as get_current_user but returns None instead of raising.

    Returns:
        User object if authenticated, None otherwise.
    """
    return _extract_user(request)


def _extract_user(request: Request) -> User | None:
    """Attempt to extract a user from request credentials.

    Args:
        request: The incoming FastAPI request.

    Returns:
        User if valid credentials found, None otherwise.
    """
    # 1. Check Authorization: Bearer <token> header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Strip "Bearer " prefix
        try:
            payload = AuthService.verify_token(token)
            user = AuthService.get_user_by_id(payload["user_id"], _DB_PATH)
            if user and user.is_active:
                return user
        except ValueError:
            logger.debug("Invalid Bearer token received")

    # 2. Check X-API-Key header
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        user = AuthService.verify_api_key(api_key_header, _DB_PATH)
        if user:
            return user
        logger.debug("Invalid X-API-Key header received")

    # 3. Check api_key query parameter
    api_key_param = request.query_params.get("api_key")
    if api_key_param:
        user = AuthService.verify_api_key(api_key_param, _DB_PATH)
        if user:
            return user
        logger.debug("Invalid api_key query parameter received")

    return None
