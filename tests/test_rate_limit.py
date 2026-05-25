"""Tests for API rate limiting (src.api.rate_limit).

Verifies SlidingWindowLimiter behavior, path-based filtering,
and per-user isolation.
"""

from __future__ import annotations

from unittest.mock import patch

from src.api.rate_limit import SlidingWindowLimiter, _should_rate_limit


class TestShouldRateLimit:
    """Tests for the _should_rate_limit() path filtering function."""

    def test_health_skips_rate_limiting(self):
        """/health endpoint should not be rate limited."""
        assert _should_rate_limit("/health") is False

    def test_score_is_rate_limited(self):
        """/score endpoint should be rate limited."""
        assert _should_rate_limit("/score") is True

    def test_history_is_rate_limited(self):
        """/history endpoint should be rate limited."""
        assert _should_rate_limit("/history") is True

    def test_static_files_skip_rate_limiting(self):
        """Static file paths should not be rate limited."""
        assert _should_rate_limit("/static/style.css") is False

    def test_docs_skip_rate_limiting(self):
        """/docs and /openapi.json should not be rate limited."""
        assert _should_rate_limit("/docs") is False
        assert _should_rate_limit("/openapi.json") is False

    def test_auth_paths_are_rate_limited(self):
        """/auth/* paths should be rate limited."""
        assert _should_rate_limit("/auth/login") is True
        assert _should_rate_limit("/auth/register") is True


class TestSlidingWindowLimiter:
    """Tests for the SlidingWindowLimiter class."""

    def test_requests_within_limit_allowed(self):
        """Requests under the limit are allowed."""
        limiter = SlidingWindowLimiter()
        for i in range(5):
            assert limiter.is_allowed("user:1", limit=5) is True

    def test_requests_exceeding_limit_rejected(self):
        """Requests over the limit are rejected."""
        limiter = SlidingWindowLimiter()
        for i in range(5):
            limiter.is_allowed("user:1", limit=5)
        # 6th request should be rejected
        assert limiter.is_allowed("user:1", limit=5) is False

    def test_after_window_passes_requests_allowed_again(self):
        """After the time window passes, requests are allowed again."""
        limiter = SlidingWindowLimiter()

        # Fill up the limit at time=1000
        with patch("src.api.rate_limit.time.time", return_value=1000.0):
            for i in range(5):
                limiter.is_allowed("user:1", limit=5, window_seconds=60)
            # Should be rejected
            assert limiter.is_allowed("user:1", limit=5, window_seconds=60) is False

        # After the window passes (61 seconds later)
        with patch("src.api.rate_limit.time.time", return_value=1061.0):
            assert limiter.is_allowed("user:1", limit=5, window_seconds=60) is True

    def test_per_user_isolation(self):
        """Different user keys do not interfere with each other."""
        limiter = SlidingWindowLimiter()
        # Fill up user:1 limit
        for i in range(3):
            limiter.is_allowed("user:1", limit=3)
        assert limiter.is_allowed("user:1", limit=3) is False
        # user:2 should still be allowed
        assert limiter.is_allowed("user:2", limit=3) is True

    def test_get_remaining_decreases(self):
        """get_remaining() reflects remaining capacity."""
        limiter = SlidingWindowLimiter()
        assert limiter.get_remaining("user:1", limit=5) == 5
        limiter.is_allowed("user:1", limit=5)
        assert limiter.get_remaining("user:1", limit=5) == 4
        limiter.is_allowed("user:1", limit=5)
        assert limiter.get_remaining("user:1", limit=5) == 3

    def test_empty_key_returns_full_limit(self):
        """A key with no requests has full remaining capacity."""
        limiter = SlidingWindowLimiter()
        assert limiter.get_remaining("new_key", limit=10) == 10
