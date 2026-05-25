"""API rate limiting — sliding window, per-user and global.

Limits:
- Authenticated users: configurable per-user limits
- Anonymous users: limited by IP address with stricter limits
- Global limit: total requests per minute across all users
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("rate_limit")


@dataclass
class RateLimitConfig:
    """Configuration for API rate limiting."""

    authenticated_rpm: int = 30  # requests per minute for authenticated users
    anonymous_rpm: int = 10  # requests per minute for anonymous (by IP)
    global_rpm: int = 100  # total requests per minute across all users
    score_endpoint_rpm: int = 10  # stricter limit for /score (LLM cost control)
    burst_allowance: int = 5  # extra burst allowed above limit


class SlidingWindowLimiter:
    """In-memory sliding window rate limiter using deques of timestamps.

    Thread-safe under CPython's GIL for single-process deployments.
    Automatically prunes keys older than 5 minutes to prevent memory leaks.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._last_prune: float = time.time()
        self._prune_interval: float = 300.0  # prune every 5 minutes

    def is_allowed(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        """Check if a request is within the rate limit.

        Args:
            key: Identifier for the rate limit bucket (e.g. "user:123" or "ip:1.2.3.4")
            limit: Maximum number of requests allowed in the window
            window_seconds: Size of the sliding window in seconds

        Returns:
            True if the request is allowed, False if rate limited
        """
        now = time.time()
        self._cleanup(key, window_seconds, now)
        self._maybe_prune(now)

        if key not in self._windows:
            self._windows[key] = deque()

        window = self._windows[key]

        if len(window) < limit:
            window.append(now)
            return True

        return False

    def get_remaining(self, key: str, limit: int, window_seconds: int = 60) -> int:
        """Get the number of remaining requests allowed in the current window.

        Args:
            key: Identifier for the rate limit bucket
            limit: Maximum number of requests allowed in the window
            window_seconds: Size of the sliding window in seconds

        Returns:
            Number of remaining requests allowed
        """
        now = time.time()
        self._cleanup(key, window_seconds, now)

        if key not in self._windows:
            return limit

        return max(0, limit - len(self._windows[key]))

    def _cleanup(self, key: str, window_seconds: int, now: float | None = None) -> None:
        """Remove expired timestamps from a specific key's window.

        Args:
            key: Identifier for the rate limit bucket
            window_seconds: Size of the sliding window in seconds
            now: Current timestamp (defaults to time.time())
        """
        if now is None:
            now = time.time()

        if key not in self._windows:
            return

        window = self._windows[key]
        cutoff = now - window_seconds

        # Remove all timestamps older than the window
        while window and window[0] <= cutoff:
            window.popleft()

        # Remove empty keys to save memory
        if not window:
            del self._windows[key]

    def _maybe_prune(self, now: float) -> None:
        """Periodically prune all keys with no recent activity (older than 5 minutes).

        This prevents unbounded memory growth from abandoned keys.
        """
        if now - self._last_prune < self._prune_interval:
            return

        self._last_prune = now
        cutoff = now - self._prune_interval

        keys_to_remove = []
        for key, window in self._windows.items():
            if not window or window[-1] < cutoff:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._windows[key]

        if keys_to_remove:
            logger.debug("Pruned %d stale rate limit keys", len(keys_to_remove))


# Paths that should skip rate limiting entirely
_SKIP_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})
_SKIP_PREFIXES = ("/static/",)

# API paths that SHOULD be rate limited
_RATE_LIMITED_PATHS = frozenset({"/score", "/history"})
_RATE_LIMITED_PREFIXES = ("/auth/", "/preferences/", "/api/")


def _should_rate_limit(path: str) -> bool:
    """Determine if a request path should be rate limited.

    Rate limiting applies to:
    - /score, /history endpoints
    - /auth/*, /preferences/* routes
    - Any path containing /api/

    Skips:
    - /health, /docs, /openapi.json
    - /static/* files
    - Web UI pages (all other paths)
    """
    # Explicit skip paths
    if path in _SKIP_PATHS:
        return False

    # Skip static files
    for prefix in _SKIP_PREFIXES:
        if path.startswith(prefix):
            return False

    # Rate limit known API paths
    if path in _RATE_LIMITED_PATHS:
        return True

    # Rate limit API prefixes
    for prefix in _RATE_LIMITED_PREFIXES:
        if path.startswith(prefix):
            return True

    # Everything else (web UI pages) — don't rate limit
    return False


def _extract_client_identity(request: Request) -> tuple[str, bool]:
    """Extract client identity from the request.

    Returns:
        Tuple of (identity_key, is_authenticated)
        - For authenticated users: ("user:{user_id}", True)
        - For anonymous users: ("ip:{client_ip}", False)
    """
    # Check for authentication headers
    auth_header = request.headers.get("authorization", "")
    api_key = request.headers.get("x-api-key", "")

    if auth_header.startswith("Bearer ") and len(auth_header) > 7:
        # Use the token as a proxy for user identity
        # In a real app, you'd decode the JWT to get the user_id
        # For now, hash the token to create a consistent key
        token = auth_header[7:]
        # Use first 16 chars of token as key (enough for uniqueness)
        return f"user:{token[:16]}", True

    if api_key:
        return f"user:{api_key[:16]}", True

    # Anonymous — use client IP
    client_ip = _get_client_ip(request)
    return f"ip:{client_ip}", False


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, respecting X-Forwarded-For header."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()

    # Fall back to direct connection IP
    if request.client:
        return request.client.host

    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for API rate limiting.

    Applies per-user and global sliding window rate limits.
    Returns 429 responses with retry information when limits are exceeded.
    Adds rate limit headers to all responses.
    """

    def __init__(self, app, config: RateLimitConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.limiter = SlidingWindowLimiter()
        self._global_limiter = SlidingWindowLimiter()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request through rate limiting."""
        path = request.url.path

        # Skip rate limiting for non-API paths
        if not _should_rate_limit(path):
            return await call_next(request)

        # Extract client identity
        identity_key, is_authenticated = _extract_client_identity(request)

        # Determine the applicable limit
        if path == "/score" or path.startswith("/score"):
            # Stricter limit for /score endpoint (LLM cost control)
            per_user_limit = self.config.score_endpoint_rpm + self.config.burst_allowance
        elif is_authenticated:
            per_user_limit = self.config.authenticated_rpm + self.config.burst_allowance
        else:
            per_user_limit = self.config.anonymous_rpm + self.config.burst_allowance

        global_limit = self.config.global_rpm + self.config.burst_allowance

        # Check global rate limit first
        if not self._global_limiter.is_allowed("global", global_limit):
            logger.warning("Global rate limit exceeded (limit=%d rpm)", self.config.global_rpm)
            retry_after = 60  # suggest retry after 1 minute
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.config.global_rpm),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Check per-user rate limit
        if not self.limiter.is_allowed(identity_key, per_user_limit):
            # Calculate the base limit (without burst) for logging
            if path == "/score" or path.startswith("/score"):
                base_limit = self.config.score_endpoint_rpm
            elif is_authenticated:
                base_limit = self.config.authenticated_rpm
            else:
                base_limit = self.config.anonymous_rpm

            logger.warning(
                "Rate limit exceeded for %s on %s (limit=%d rpm)",
                identity_key,
                path,
                base_limit,
            )
            retry_after = 60
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(base_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Request is allowed — process it
        response = await call_next(request)

        # Add rate limit headers to successful responses
        if path == "/score" or path.startswith("/score"):
            base_limit = self.config.score_endpoint_rpm
        elif is_authenticated:
            base_limit = self.config.authenticated_rpm
        else:
            base_limit = self.config.anonymous_rpm

        remaining = self.limiter.get_remaining(identity_key, per_user_limit)
        response.headers["X-RateLimit-Limit"] = str(base_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 60)

        return response
