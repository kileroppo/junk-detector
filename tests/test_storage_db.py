"""Tests for src/storage/db.py — SQLite storage layer."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.storage.db import (
    get_all_embeddings,
    get_history,
    init_db,
    query,
    query_by_content_hash,
    query_by_domain,
    save,
)


@pytest.fixture
def db(tmp_db_path):
    """Initialize storage db and return path."""
    init_db(tmp_db_path)
    return tmp_db_path


@pytest.fixture
def sample_content():
    """Create a sample Content for test use."""
    content = Content(
        input_type=InputType.TEXT,
        text="Test content for storage",
        title="Test Article",
        source_url="https://example.com/article",
    )
    content.compute_hash()
    return content


@pytest.fixture
def sample_result():
    """Create a sample ScoreResult for test use."""
    return ScoreResult(
        overall_score=72.5,
        dimensions=DimensionScores(
            originality=80,
            info_density=70,
            reasoning_quality=75,
            readability=85,
            timeliness=60,
            ai_generated_prob=15,
            emotional_manipulation=10,
            advertorial_prob=20,
            scam_prob=5,
        ),
        labels=["高质量原创"],
        summary="A good quality article",
        confidence=0.9,
        model_used="test-model",
        cost=0.001,
    )


class TestInitDb:
    """Tests for init_db."""

    def test_creates_scores_table(self, tmp_db_path):
        """init_db creates the scores table."""
        init_db(tmp_db_path)
        # No exception means success
        # Verify by saving a record
        content = Content(input_type=InputType.TEXT, text="test", title="t")
        content.compute_hash()
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50, info_density=50, reasoning_quality=50,
                readability=50, timeliness=50, ai_generated_prob=50,
                emotional_manipulation=50, advertorial_prob=50, scam_prob=50,
            ),
            labels=[],
            summary="test",
        )
        save(result, content, tmp_db_path)
        records = get_history(limit=1, db_path=tmp_db_path)
        assert len(records) == 1


class TestSave:
    """Tests for save."""

    def test_save_and_retrieve(self, db, sample_content, sample_result):
        """save stores record retrievable by content hash."""
        save(sample_result, sample_content, db)

        record = query_by_content_hash(sample_content.content_hash, db)
        assert record is not None
        assert record["overall_score"] == 72.5
        assert record["title"] == "Test Article"

    def test_save_with_embedding(self, db, sample_content, sample_result):
        """save stores embedding when provided."""
        embedding = [0.1, 0.2, 0.3, 0.4]
        save(sample_result, sample_content, db, embedding=embedding)

        records = get_all_embeddings(db)
        assert len(records) == 1
        assert records[0]["embedding"] == embedding

    def test_save_upserts_on_duplicate_hash(self, db, sample_content, sample_result):
        """save upserts when content_hash already exists."""
        save(sample_result, sample_content, db)

        # Update score and save again
        sample_result.overall_score = 85.0
        save(sample_result, sample_content, db)

        record = query_by_content_hash(sample_content.content_hash, db)
        assert record["overall_score"] == 85.0


class TestQuery:
    """Tests for query."""

    def test_query_with_no_filters(self, db, sample_content, sample_result):
        """query with no filters returns all records."""
        save(sample_result, sample_content, db)

        results = query(db_path=db)
        assert len(results) == 1

    def test_query_with_min_score_filter(self, db, sample_content, sample_result):
        """query with min_score filter works correctly."""
        save(sample_result, sample_content, db)

        results = query(filters={"min_score": 80.0}, db_path=db)
        assert len(results) == 0

        results = query(filters={"min_score": 70.0}, db_path=db)
        assert len(results) == 1

    def test_query_with_max_score_filter(self, db, sample_content, sample_result):
        """query with max_score filter works correctly."""
        save(sample_result, sample_content, db)

        results = query(filters={"max_score": 50.0}, db_path=db)
        assert len(results) == 0

        results = query(filters={"max_score": 80.0}, db_path=db)
        assert len(results) == 1

    def test_query_with_label_filter(self, db, sample_content, sample_result):
        """query with label filter matches labels_json."""
        save(sample_result, sample_content, db)

        results = query(filters={"label": "高质量原创"}, db_path=db)
        assert len(results) == 1

        results = query(filters={"label": "疑似骗局"}, db_path=db)
        assert len(results) == 0


class TestGetHistory:
    """Tests for get_history."""

    def test_returns_recent_records(self, db, sample_content, sample_result):
        """get_history returns records."""
        save(sample_result, sample_content, db)
        records = get_history(limit=10, db_path=db)
        assert len(records) == 1

    def test_empty_db_returns_empty(self, db):
        """get_history on empty db returns empty list."""
        records = get_history(db_path=db)
        assert records == []


class TestQueryByContentHash:
    """Tests for query_by_content_hash."""

    def test_found(self, db, sample_content, sample_result):
        """query_by_content_hash returns record when found."""
        save(sample_result, sample_content, db)
        record = query_by_content_hash(sample_content.content_hash, db)
        assert record is not None

    def test_not_found(self, db):
        """query_by_content_hash returns None when not found."""
        record = query_by_content_hash("nonexistent_hash", db)
        assert record is None


class TestQueryByDomain:
    """Tests for query_by_domain."""

    def test_matches_domain(self, db, sample_content, sample_result):
        """query_by_domain returns scores for matching domain."""
        save(sample_result, sample_content, db)
        scores = query_by_domain("example.com", db)
        assert len(scores) == 1
        assert scores[0] == 72.5

    def test_no_match(self, db, sample_content, sample_result):
        """query_by_domain returns empty for non-matching domain."""
        save(sample_result, sample_content, db)
        scores = query_by_domain("other.org", db)
        assert len(scores) == 0


class TestGetAllEmbeddings:
    """Tests for get_all_embeddings."""

    def test_returns_records_with_embeddings(self, db, sample_content, sample_result):
        """get_all_embeddings returns records that have embeddings."""
        embedding = [1.0, 2.0, 3.0]
        save(sample_result, sample_content, db, embedding=embedding)

        results = get_all_embeddings(db)
        assert len(results) == 1
        assert results[0]["content_hash"] == sample_content.content_hash
        assert results[0]["embedding"] == embedding

    def test_empty_when_no_embeddings(self, db, sample_content, sample_result):
        """get_all_embeddings returns empty when no records have embeddings."""
        save(sample_result, sample_content, db)  # No embedding
        results = get_all_embeddings(db)
        assert results == []
