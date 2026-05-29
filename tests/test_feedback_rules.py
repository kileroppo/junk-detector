"""Tests for the feedback-to-rules pipeline (save_feedback_with_content, suggest_new_rules, migration)."""

from __future__ import annotations

import sqlite3

import pytest

from src.core.calibration import (
    _initialized_feedback_dbs,
    init_feedback_db,
    save_feedback_with_content,
    suggest_new_rules,
)
from src.storage.db import _get_connection


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    db_file = str(tmp_path / "test_feedback.db")

    # Clear the initialized cache so init runs fresh
    _initialized_feedback_dbs.discard(db_file)

    # Patch _get_connection to use the temp file
    original_get_connection = _get_connection

    def patched_get_connection(db_path):
        if db_path == db_file:
            return original_get_connection(db_file)
        return original_get_connection(db_path)

    monkeypatch.setattr("src.core.calibration._get_connection", patched_get_connection)

    return db_file


@pytest.fixture()
def temp_db_v1(tmp_path, monkeypatch):
    """Create a temp database with the old v1 feedback schema (no content_text/original_score)."""
    db_file = str(tmp_path / "test_feedback_v1.db")

    # Create the old-style table manually
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL,
            user_verdict TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    # Clear the initialized cache
    _initialized_feedback_dbs.discard(db_file)

    original_get_connection = _get_connection

    def patched_get_connection(db_path):
        if db_path == db_file:
            return original_get_connection(db_file)
        return original_get_connection(db_path)

    monkeypatch.setattr("src.core.calibration._get_connection", patched_get_connection)

    return db_file


class TestSaveFeedbackWithContent:
    """Test save_feedback_with_content stores content_text and original_score."""

    def test_stores_content_and_score(self, temp_db):
        """Feedback with content text and score is properly stored."""
        save_feedback_with_content(
            content_hash="abc123",
            content_text="This is test content",
            user_verdict="junk",
            original_score=75.0,
            db_path=temp_db,
        )

        conn = _get_connection(temp_db)
        try:
            cursor = conn.execute("SELECT * FROM feedback WHERE content_hash = 'abc123'")
            row = cursor.fetchone()
            assert row is not None
            assert row["content_text"] == "This is test content"
            assert row["original_score"] == 75.0
            assert row["user_verdict"] == "junk"
        finally:
            conn.close()

    def test_stores_multiple_entries(self, temp_db):
        """Multiple feedback entries can be stored."""
        save_feedback_with_content("hash1", "Content 1", "junk", 80.0, db_path=temp_db)
        save_feedback_with_content("hash2", "Content 2", "ok", 50.0, db_path=temp_db)
        save_feedback_with_content("hash3", "Content 3", "excellent", 20.0, db_path=temp_db)

        conn = _get_connection(temp_db)
        try:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM feedback")
            assert cursor.fetchone()["cnt"] == 3
        finally:
            conn.close()

    def test_invalid_verdict_raises(self, temp_db):
        """Invalid verdict raises ValueError."""
        with pytest.raises(ValueError, match="Invalid verdict"):
            save_feedback_with_content("hash1", "text", "bad_verdict", 50.0, db_path=temp_db)


class TestSuggestNewRules:
    """Test suggest_new_rules returns structured rule candidates."""

    def test_returns_empty_with_no_data(self, temp_db):
        """Returns empty list when no feedback data exists."""
        # Initialize the DB
        init_feedback_db(temp_db)
        result = suggest_new_rules(db_path=temp_db)
        assert result == []

    def test_returns_empty_with_insufficient_data(self, temp_db):
        """Returns empty list when feedback count is below min_count."""
        # Add only 1 feedback entry (below default min_count=3)
        save_feedback_with_content(
            "hash1", "免费赚钱加微信", "junk", 75.0, db_path=temp_db
        )

        result = suggest_new_rules(min_count=3, db_path=temp_db)
        assert result == []

    def test_returns_structured_rules_with_sufficient_data(self, temp_db):
        """Returns rule candidates when given sufficient false negative feedback."""
        # Add 4 entries with overlapping scam keywords (user=junk, score>=40)
        texts = [
            "免费领取大礼包赚钱加微信转账",
            "加微信免费领取暴富秘籍",
            "转账即可免费获得赚钱机会加微信",
            "加微信免费试用暴富计划",
        ]
        for i, text in enumerate(texts):
            save_feedback_with_content(f"hash{i}", text, "junk", 75.0, db_path=temp_db)

        result = suggest_new_rules(min_count=3, db_path=temp_db)

        assert len(result) > 0
        # Check structure of returned rules
        for rule in result:
            assert "name" in rule
            assert "keywords" in rule
            assert "target_dimension" in rule
            assert "score_contribution" in rule
            assert "confidence" in rule
            assert isinstance(rule["keywords"], list)
            assert rule["target_dimension"] in (
                "scam_prob",
                "advertorial_prob",
                "emotional_manipulation",
                "ai_generated_prob",
            )
            assert 0 <= rule["confidence"] <= 1.0

    def test_returns_empty_when_no_false_negatives(self, temp_db):
        """Returns empty when user verdicts agree with system (no false negatives)."""
        # User says ok on content scored highly - not a false negative
        save_feedback_with_content("hash1", "Good content text", "ok", 80.0, db_path=temp_db)
        save_feedback_with_content("hash2", "Nice article here", "ok", 70.0, db_path=temp_db)
        save_feedback_with_content("hash3", "Excellent article", "excellent", 90.0, db_path=temp_db)

        result = suggest_new_rules(min_count=1, db_path=temp_db)
        assert result == []

    def test_only_considers_false_negatives(self, temp_db):
        """Only content marked junk with score>=40 is considered."""
        # True positive (user=junk, score<40) - should not be considered
        save_feedback_with_content("hash1", "加微信免费转账赚钱", "junk", 20.0, db_path=temp_db)
        save_feedback_with_content("hash2", "加微信免费转账暴富", "junk", 30.0, db_path=temp_db)
        save_feedback_with_content("hash3", "加微信免费获取赚钱", "junk", 15.0, db_path=temp_db)

        result = suggest_new_rules(min_count=3, db_path=temp_db)
        # These are true positives (system already caught them), not false negatives
        assert result == []


class TestFeedbackTableMigration:
    """Test the feedback table migration (add columns to existing table)."""

    def test_migrates_v1_table_to_v2(self, temp_db_v1):
        """Old v1 table gets content_text and original_score columns added."""
        # Verify old table exists without new columns
        conn = _get_connection(temp_db_v1)
        cursor = conn.execute("PRAGMA table_info(feedback)")
        old_columns = {row["name"] for row in cursor.fetchall()}
        conn.close()

        assert "content_text" not in old_columns
        assert "original_score" not in old_columns

        # Run init which should migrate
        init_feedback_db(temp_db_v1)

        # Verify new columns exist
        conn = _get_connection(temp_db_v1)
        cursor = conn.execute("PRAGMA table_info(feedback)")
        new_columns = {row["name"] for row in cursor.fetchall()}
        conn.close()

        assert "content_text" in new_columns
        assert "original_score" in new_columns

    def test_migration_preserves_existing_data(self, temp_db_v1):
        """Existing feedback data is preserved after migration."""
        # Insert data into old table
        conn = _get_connection(temp_db_v1)
        conn.execute(
            "INSERT INTO feedback (content_hash, user_verdict, created_at) VALUES (?, ?, ?)",
            ("old_hash_123", "junk", "2025-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

        # Run migration
        init_feedback_db(temp_db_v1)

        # Check old data is still there
        conn = _get_connection(temp_db_v1)
        cursor = conn.execute("SELECT * FROM feedback WHERE content_hash = 'old_hash_123'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row["user_verdict"] == "junk"
        assert row["content_text"] is None  # New column should be NULL for old data
        assert row["original_score"] is None

    def test_double_migration_is_safe(self, temp_db_v1):
        """Running init_feedback_db twice does not error."""
        init_feedback_db(temp_db_v1)

        # Clear the cache to force re-run
        _initialized_feedback_dbs.discard(temp_db_v1)

        # Should not raise
        init_feedback_db(temp_db_v1)

        conn = _get_connection(temp_db_v1)
        cursor = conn.execute("PRAGMA table_info(feedback)")
        columns = {row["name"] for row in cursor.fetchall()}
        conn.close()

        assert "content_text" in columns
        assert "original_score" in columns
