"""Tests for the deduplication layer (src.core.dedup).

Verifies TTLCache expiration, maxsize eviction, and should_score behavior.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.dedup import TTLCache, reset_cache, should_score


class TestTTLCache:
    """Tests for the TTLCache class."""

    def test_new_key_not_in_cache(self):
        """A key not previously added is not in the cache."""
        cache = TTLCache(maxsize=100, ttl=60.0)
        assert "test_key" not in cache

    def test_added_key_is_in_cache(self):
        """A key that was added is found in the cache."""
        cache = TTLCache(maxsize=100, ttl=60.0)
        cache.add("test_key")
        assert "test_key" in cache

    def test_key_expires_after_ttl(self):
        """After TTL expires, the key should no longer be in the cache."""
        cache = TTLCache(maxsize=100, ttl=5.0)
        with patch("src.core.dedup.time.time", return_value=1000.0):
            cache.add("test_key")

        # After TTL has passed
        with patch("src.core.dedup.time.time", return_value=1006.0):
            assert "test_key" not in cache

    def test_maxsize_eviction(self):
        """When maxsize is exceeded, oldest entries are evicted."""
        cache = TTLCache(maxsize=3, ttl=60.0)
        cache.add("key1")
        cache.add("key2")
        cache.add("key3")
        cache.add("key4")  # This should evict key1
        assert "key1" not in cache
        assert "key4" in cache

    def test_size_property(self):
        """Size property reflects the number of stored entries."""
        cache = TTLCache(maxsize=100, ttl=60.0)
        assert cache.size == 0
        cache.add("a")
        cache.add("b")
        assert cache.size == 2


class TestShouldScore:
    """Tests for the should_score() function."""

    def test_first_call_returns_true(self):
        """First time seeing content returns True (should score it)."""
        assert should_score("https://example.com/article") is True

    def test_immediate_second_call_returns_false(self):
        """Same content immediately after returns False (skip it)."""
        should_score("https://example.com/same")
        assert should_score("https://example.com/same") is False

    def test_different_content_returns_true(self):
        """Different content returns True even if cache has other entries."""
        should_score("content A")
        assert should_score("content B") is True

    def test_reset_cache_clears_all(self):
        """After reset_cache(), previously seen content returns True again."""
        should_score("https://example.com/test")
        assert should_score("https://example.com/test") is False
        reset_cache()
        assert should_score("https://example.com/test") is True
