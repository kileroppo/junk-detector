"""Deduplication layer — prevents scoring the same content within a short window.

Uses TTLCache to track recently scored URLs/content hashes.
Inspired by x-algorithm's task rate limiting pattern.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict

logger = logging.getLogger("dedup")


class TTLCache:
    """Simple TTL cache using OrderedDict. No external dependencies.

    Keys expire after `ttl` seconds. Max `maxsize` entries.
    Thread-safe under CPython GIL.
    """

    def __init__(self, maxsize: int = 10000, ttl: float = 60.0):
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: OrderedDict[str, float] = OrderedDict()

    def __contains__(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        if key not in self._cache:
            return False
        if time.time() - self._cache[key] > self._ttl:
            del self._cache[key]
            return False
        return True

    def add(self, key: str) -> None:
        """Add a key with current timestamp."""
        self._cleanup()
        self._cache[key] = time.time()
        # Evict oldest if over maxsize
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def _cleanup(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, t in self._cache.items() if now - t > self._ttl]
        for k in expired:
            del self._cache[k]

    @property
    def size(self) -> int:
        """Current number of entries (including possibly expired)."""
        return len(self._cache)


# Global dedup cache (60 second window, max 10K entries)
_score_cache = TTLCache(maxsize=10000, ttl=60.0)


def should_score(url_or_text: str) -> bool:
    """Check if this content should be scored or was recently scored.

    Args:
        url_or_text: URL or text content to check.

    Returns:
        True if the content should be scored (not recently seen).
        False if it was scored within the TTL window (skip it).
    """
    # Generate a consistent key
    key = _make_key(url_or_text)

    if key in _score_cache:
        logger.debug(f"Dedup hit: skipping recently scored content (key={key[:12]}...)")
        return False

    # Mark as scored
    _score_cache.add(key)
    return True


def _make_key(content: str) -> str:
    """Generate a dedup key from URL or content text."""
    # For URLs, use the URL directly as key (normalized)
    if content.startswith(("http://", "https://")):
        return f"url:{content.strip().lower()}"
    # For text content, hash it
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"hash:{h}"


def reset_cache() -> None:
    """Reset the dedup cache. Useful for testing."""
    global _score_cache
    _score_cache = TTLCache(maxsize=10000, ttl=60.0)


def get_cache_stats() -> dict:
    """Return cache statistics."""
    return {
        "size": _score_cache.size,
        "maxsize": _score_cache._maxsize,
        "ttl_seconds": _score_cache._ttl,
    }
