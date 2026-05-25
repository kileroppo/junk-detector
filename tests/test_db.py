"""Tests for the storage layer (src.storage.db).

Verifies query_by_domain wildcard escaping and query_by_content_hash behavior.
"""
from __future__ import annotations

import json

import pytest

from src.storage.db import init_db, query_by_content_hash, query_by_domain, save
from src.models.score import Content, DimensionScores, InputType, ScoreResult


def _make_result(overall_score: float = 50.0, source_url: str = "https://example.com") -> tuple[ScoreResult, Content]:
    """Create a minimal ScoreResult and Content for testing."""
    result = ScoreResult(
        overall_score=overall_score,
        dimensions=DimensionScores(
            originality=50, info_density=50, reasoning_quality=50,
            readability=50, timeliness=50, ai_generated_prob=50,
            emotional_manipulation=50, advertorial_prob=50, scam_prob=50,
        ),
        labels=[],
        summary="test",
        confidence=0.8,
        model_used="test-model",
        cost=0.0,
    )
    content = Content(
        input_type=InputType.URL,
        text=f"content for {source_url}",
        source_url=source_url,
        title="Test",
        content_hash="",
    )
    content.compute_hash()
    return result, content


class TestQueryByDomain:
    """Tests for query_by_domain with wildcard escaping."""

    def test_basic_domain_query(self, tmp_db_path):
        """Basic domain lookup returns matching scores."""
        init_db(tmp_db_path)
        result, content = _make_result(75.0, "https://example.com/article1")
        save(result, content, db_path=tmp_db_path)

        scores = query_by_domain("example.com", db_path=tmp_db_path)
        assert len(scores) == 1
        assert scores[0] == 75.0

    def test_domain_with_percent_is_escaped(self, tmp_db_path):
        """A domain containing % does not act as a SQL wildcard."""
        init_db(tmp_db_path)
        # Save a record with a normal domain
        result1, content1 = _make_result(60.0, "https://normal-site.com/page")
        save(result1, content1, db_path=tmp_db_path)

        # Query with % in domain - should NOT match anything
        scores = query_by_domain("normal%site", db_path=tmp_db_path)
        assert len(scores) == 0

    def test_domain_with_underscore_is_escaped(self, tmp_db_path):
        """A domain containing _ does not act as a SQL single-char wildcard."""
        init_db(tmp_db_path)
        # Save records
        result1, content1 = _make_result(70.0, "https://my-site.com/page")
        save(result1, content1, db_path=tmp_db_path)

        # _ should not match any single character
        scores = query_by_domain("my_site", db_path=tmp_db_path)
        assert len(scores) == 0

    def test_domain_no_matches_returns_empty(self, tmp_db_path):
        """When no records match the domain, returns empty list."""
        init_db(tmp_db_path)
        result, content = _make_result(80.0, "https://other.com/article")
        save(result, content, db_path=tmp_db_path)

        scores = query_by_domain("nonexistent.com", db_path=tmp_db_path)
        assert len(scores) == 0

    def test_multiple_matches(self, tmp_db_path):
        """Multiple records from same domain are all returned."""
        init_db(tmp_db_path)
        result1, content1 = _make_result(60.0, "https://news.example.com/a")
        save(result1, content1, db_path=tmp_db_path)

        result2, content2 = _make_result(80.0, "https://news.example.com/b")
        save(result2, content2, db_path=tmp_db_path)

        scores = query_by_domain("news.example.com", db_path=tmp_db_path)
        assert len(scores) == 2
        assert set(scores) == {60.0, 80.0}


class TestQueryByContentHash:
    """Tests for query_by_content_hash."""

    def test_returns_none_when_not_found(self, tmp_db_path):
        """Returns None when no record matches the hash."""
        init_db(tmp_db_path)
        result = query_by_content_hash("nonexistent_hash", db_path=tmp_db_path)
        assert result is None

    def test_returns_record_when_found(self, tmp_db_path):
        """Returns the matching record when hash exists."""
        init_db(tmp_db_path)
        score_result, content = _make_result(72.0, "https://example.com/test")
        save(score_result, content, db_path=tmp_db_path)

        result = query_by_content_hash(content.content_hash, db_path=tmp_db_path)
        assert result is not None
        assert result["overall_score"] == 72.0
        assert "dimensions" in result
