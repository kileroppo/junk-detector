"""Tests for the storage layer (src.storage.db).

Verifies query_by_domain wildcard escaping and query_by_content_hash behavior.
"""

from __future__ import annotations

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.storage.db import init_db, query, query_by_content_hash, query_by_domain, save


def _make_result(
    overall_score: float = 50.0, source_url: str = "https://example.com"
) -> tuple[ScoreResult, Content]:
    """Create a minimal ScoreResult and Content for testing."""
    result = ScoreResult(
        overall_score=overall_score,
        dimensions=DimensionScores(
            originality=50,
            info_density=50,
            reasoning_quality=50,
            readability=50,
            timeliness=50,
            ai_generated_prob=50,
            emotional_manipulation=50,
            advertorial_prob=50,
            scam_prob=50,
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


class TestSaveWithUserId:
    """Tests for save() and query() with user_id parameter."""

    def test_save_with_user_id_stores_value(self, tmp_db_path):
        """Saving with user_id stores the value in the user_id column."""
        init_db(tmp_db_path)
        result, content = _make_result(65.0, "https://example.com/user42")
        save(result, content, db_path=tmp_db_path, user_id=42)

        rows = query(db_path=tmp_db_path)
        assert len(rows) == 1
        assert rows[0]["user_id"] == 42

    def test_save_without_user_id_stores_null(self, tmp_db_path):
        """Saving without user_id stores NULL."""
        init_db(tmp_db_path)
        result, content = _make_result(55.0, "https://example.com/anon")
        save(result, content, db_path=tmp_db_path)

        rows = query(db_path=tmp_db_path)
        assert len(rows) == 1
        assert rows[0]["user_id"] is None

    def test_query_filters_by_user_id(self, tmp_db_path):
        """Query with user_id returns only that user's records."""
        init_db(tmp_db_path)
        result1, content1 = _make_result(70.0, "https://example.com/user1")
        save(result1, content1, db_path=tmp_db_path, user_id=1)

        result2, content2 = _make_result(80.0, "https://example.com/user2")
        save(result2, content2, db_path=tmp_db_path, user_id=2)

        rows = query(db_path=tmp_db_path, user_id=1)
        assert len(rows) == 1
        assert rows[0]["overall_score"] == 70.0
        assert rows[0]["user_id"] == 1

    def test_save_different_user_same_content_does_not_overwrite(self, tmp_db_path):
        """Saving with different user_id on same content_hash does not corrupt first user's data."""
        init_db(tmp_db_path)
        # User A scores content first
        result_a, content_a = _make_result(70.0, "https://example.com/shared")
        save(result_a, content_a, db_path=tmp_db_path, user_id=1)

        # User B scores identical content (same content_hash)
        result_b, content_b = _make_result(85.0, "https://example.com/shared")
        # content_b has same content_hash as content_a since same URL/text
        save(result_b, content_b, db_path=tmp_db_path, user_id=2)

        # User A's row should be unchanged
        rows_a = query(db_path=tmp_db_path, user_id=1)
        assert len(rows_a) == 1
        assert rows_a[0]["user_id"] == 1
        assert rows_a[0]["overall_score"] == 70.0

        # User B should have no record (upsert was skipped due to WHERE clause)
        rows_b = query(db_path=tmp_db_path, user_id=2)
        assert len(rows_b) == 0

    def test_save_same_user_same_content_does_update(self, tmp_db_path):
        """Saving with same user_id on same content_hash updates the row."""
        init_db(tmp_db_path)
        result1, content1 = _make_result(70.0, "https://example.com/rescore")
        save(result1, content1, db_path=tmp_db_path, user_id=1)

        # Same user re-scores: should update
        result2, content2 = _make_result(85.0, "https://example.com/rescore")
        save(result2, content2, db_path=tmp_db_path, user_id=1)

        rows = query(db_path=tmp_db_path, user_id=1)
        assert len(rows) == 1
        assert rows[0]["overall_score"] == 85.0

    def test_save_null_user_then_authenticated_user_updates(self, tmp_db_path):
        """Anonymous save (user_id=NULL) can be updated by any user."""
        init_db(tmp_db_path)
        # Anonymous user scores first
        result1, content1 = _make_result(60.0, "https://example.com/anon-first")
        save(result1, content1, db_path=tmp_db_path, user_id=None)

        # Authenticated user scores same content - should update (WHERE user_id IS NULL)
        result2, content2 = _make_result(75.0, "https://example.com/anon-first")
        save(result2, content2, db_path=tmp_db_path, user_id=5)

        rows = query(db_path=tmp_db_path)
        assert len(rows) == 1
        # The row was updated (user_id stays NULL because user_id is not in UPDATE SET)
        assert rows[0]["overall_score"] == 75.0
