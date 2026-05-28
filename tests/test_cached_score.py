"""Tests for get_cached_score in src.storage.db."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.storage.db import get_cached_score, init_db, save


def _make_content(text: str = "test content") -> Content:
    """Create a Content object for testing."""
    content = Content(input_type=InputType.TEXT, text=text, title="Test")
    content.compute_hash()
    return content


def _make_result(overall_score: float = 72.0) -> ScoreResult:
    """Create a ScoreResult for testing."""
    return ScoreResult(
        overall_score=overall_score,
        dimensions=DimensionScores(
            originality=70,
            info_density=60,
            reasoning_quality=65,
            readability=75,
            timeliness=50,
            ai_generated_prob=20,
            emotional_manipulation=10,
            advertorial_prob=15,
            scam_prob=5,
        ),
        labels=["test"],
        summary="Test summary",
        confidence=0.9,
        model_used="test-model",
        cost=0.001,
        scored_at=datetime.now(timezone.utc),
    )


class TestGetCachedScore:
    """Tests for get_cached_score function."""

    def test_returns_record_within_age(self, tmp_db_path):
        """Returns record when scored within max_age_days."""
        init_db(tmp_db_path)
        content = _make_content("fresh content for cache test")
        result = _make_result()
        save(result, content, db_path=tmp_db_path)

        cached = get_cached_score(content.content_hash, max_age_days=7, db_path=tmp_db_path)
        assert cached is not None
        assert cached["overall_score"] == 72.0
        assert cached["content_hash"] == content.content_hash

    def test_returns_none_when_expired(self, tmp_db_path):
        """Returns None when record is older than max_age_days."""
        init_db(tmp_db_path)
        content = _make_content("old content for cache test")
        result = _make_result()
        # Set scored_at to 10 days ago
        result.scored_at = datetime.now(timezone.utc) - timedelta(days=10)
        save(result, content, db_path=tmp_db_path)

        cached = get_cached_score(content.content_hash, max_age_days=7, db_path=tmp_db_path)
        assert cached is None

    def test_returns_none_when_not_found(self, tmp_db_path):
        """Returns None when content_hash does not exist."""
        init_db(tmp_db_path)
        cached = get_cached_score("nonexistent_hash_12345", db_path=tmp_db_path)
        assert cached is None

    def test_custom_max_age_days(self, tmp_db_path):
        """Respects custom max_age_days parameter."""
        init_db(tmp_db_path)
        content = _make_content("custom age content")
        result = _make_result()
        # Set scored_at to 3 days ago
        result.scored_at = datetime.now(timezone.utc) - timedelta(days=3)
        save(result, content, db_path=tmp_db_path)

        # Should find with 7-day window
        cached_7 = get_cached_score(content.content_hash, max_age_days=7, db_path=tmp_db_path)
        assert cached_7 is not None

        # Should not find with 2-day window
        cached_2 = get_cached_score(content.content_hash, max_age_days=2, db_path=tmp_db_path)
        assert cached_2 is None

    def test_handles_naive_datetime(self, tmp_db_path):
        """Handles records with naive (no timezone) scored_at."""
        init_db(tmp_db_path)
        content = _make_content("naive datetime content")
        result = _make_result()
        # Use naive datetime (no tzinfo) - recent
        result.scored_at = datetime.now()
        save(result, content, db_path=tmp_db_path)

        cached = get_cached_score(content.content_hash, max_age_days=7, db_path=tmp_db_path)
        assert cached is not None
