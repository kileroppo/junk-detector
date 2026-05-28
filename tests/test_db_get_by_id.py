"""Tests for src/storage/db.get_by_id() and search_records()."""

from __future__ import annotations

import pytest

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.storage.db import get_by_id, init_db, save, search_records


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
        text="Test content for get_by_id",
        title="Test Article Title",
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
            advertorial_prob=5,
            scam_prob=2,
        ),
        labels=["informative"],
        summary="A test article summary",
        model_used="test-model",
        cost=0.001,
        confidence=0.9,
    )


class TestGetById:
    """Tests for get_by_id()."""

    def test_existing_record(self, db, sample_content, sample_result):
        """get_by_id returns a record when it exists."""
        save(sample_result, sample_content, db_path=db)

        record = get_by_id(1, db_path=db)
        assert record is not None
        assert record["id"] == 1
        assert record["overall_score"] == 72.5
        assert record["title"] == "Test Article Title"

    def test_nonexistent_record(self, db):
        """get_by_id returns None for non-existing ID."""
        record = get_by_id(9999, db_path=db)
        assert record is None

    def test_returns_deserialized_dimensions(self, db, sample_content, sample_result):
        """get_by_id returns deserialized JSON fields."""
        save(sample_result, sample_content, db_path=db)

        record = get_by_id(1, db_path=db)
        assert record is not None
        assert "dimensions" in record
        assert record["dimensions"]["originality"] == 80

    def test_returns_deserialized_labels(self, db, sample_content, sample_result):
        """get_by_id returns deserialized labels."""
        save(sample_result, sample_content, db_path=db)

        record = get_by_id(1, db_path=db)
        assert record is not None
        assert "labels" in record
        assert record["labels"] == ["informative"]


class TestSearchRecords:
    """Tests for search_records()."""

    def test_search_by_title(self, db, sample_content, sample_result):
        """search_records finds records matching title."""
        save(sample_result, sample_content, db_path=db)

        results = search_records("Test Article", db_path=db)
        assert len(results) == 1
        assert results[0]["title"] == "Test Article Title"

    def test_search_by_summary(self, db, sample_content, sample_result):
        """search_records finds records matching summary."""
        save(sample_result, sample_content, db_path=db)

        results = search_records("test article summary", db_path=db)
        assert len(results) == 1

    def test_search_by_source_url(self, db, sample_content, sample_result):
        """search_records finds records matching source_url."""
        save(sample_result, sample_content, db_path=db)

        results = search_records("example.com", db_path=db)
        assert len(results) == 1

    def test_search_no_results(self, db, sample_content, sample_result):
        """search_records returns empty list when no match."""
        save(sample_result, sample_content, db_path=db)

        results = search_records("nonexistent_keyword_xyz", db_path=db)
        assert results == []

    def test_search_respects_limit(self, db):
        """search_records respects the limit parameter."""
        # Save multiple records
        for i in range(5):
            content = Content(
                input_type=InputType.TEXT,
                text=f"Content number {i} for search test",
                title=f"Search Test Article {i}",
                source_url=f"https://example.com/article-{i}",
            )
            content.compute_hash()
            result = ScoreResult(
                overall_score=50.0 + i,
                dimensions=DimensionScores(
                    originality=50,
                    info_density=50,
                    reasoning_quality=50,
                    readability=50,
                    timeliness=50,
                    ai_generated_prob=10,
                    emotional_manipulation=5,
                    advertorial_prob=5,
                    scam_prob=2,
                ),
                labels=[],
                summary=f"Summary for search test {i}",
                model_used="test-model",
                cost=0.001,
                confidence=0.9,
            )
            save(result, content, db_path=db)

        results = search_records("Search Test", limit=3, db_path=db)
        assert len(results) == 3
