"""Tests for the monthly savings report module."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from src.core.savings_report import get_savings_report


@pytest.fixture
def setup_db(tmp_path):
    """Set up a test database with required tables and sample data."""
    db_path = str(tmp_path / "test_savings.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create scores table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_type TEXT NOT NULL,
            source_url TEXT,
            title TEXT,
            content_hash TEXT UNIQUE NOT NULL,
            scored_at TEXT NOT NULL,
            overall_score REAL NOT NULL,
            dimensions_json TEXT NOT NULL,
            labels_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            model_used TEXT,
            cost REAL DEFAULT 0,
            rule_hits_json TEXT,
            confidence REAL DEFAULT 1.0,
            embedding_json TEXT
        )
    """)

    # Create scoring_stats table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scoring_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            rules_only_count INTEGER DEFAULT 0,
            llm_count INTEGER DEFAULT 0
        )
    """)

    # Create token_roi table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS token_roi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT,
            tokens_used INTEGER,
            rules_score REAL,
            llm_score REAL,
            roi REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    return db_path


class TestEmptyDB:
    """Test savings report with empty database."""

    def test_empty_db_returns_zeros(self, setup_db):
        result = get_savings_report(days=30, db_path=setup_db)
        assert result["total_scores"] == 0
        assert result["rules_only_count"] == 0
        assert result["cached_count"] == 0
        assert result["total_tokens_used"] == 0
        assert result["token_savings_percent"] == 0.0
        assert result["estimated_cost_saved_yuan"] == 0.0
        assert result["time_saved_minutes"] == 0.0

    def test_empty_db_returns_all_required_keys(self, setup_db):
        result = get_savings_report(days=30, db_path=setup_db)
        expected_keys = [
            "total_scores",
            "rules_only_count",
            "cached_count",
            "total_tokens_used",
            "estimated_tokens_if_no_optimization",
            "token_savings_percent",
            "estimated_cost_saved_yuan",
            "avg_response_time_ms",
            "estimated_time_if_manual",
            "time_saved_minutes",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


class TestWithSampleData:
    """Test savings report with sample data."""

    def test_counts_scores_in_period(self, setup_db):
        conn = sqlite3.connect(setup_db)
        now = datetime.now()

        # Add 5 scores in the last 30 days
        for i in range(5):
            scored_at = (now - timedelta(days=i)).isoformat()
            conn.execute(
                """INSERT INTO scores (input_type, content_hash, scored_at,
                   overall_score, dimensions_json, labels_json, summary, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", f"hash_{i}", scored_at, 65.0, "{}", "[]", "test", "deepseek"),
            )

        # Add 1 score outside the period (40 days ago)
        old_scored_at = (now - timedelta(days=40)).isoformat()
        conn.execute(
            """INSERT INTO scores (input_type, content_hash, scored_at,
               overall_score, dimensions_json, labels_json, summary, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("text", "hash_old", old_scored_at, 50.0, "{}", "[]", "old", "deepseek"),
        )

        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)
        assert result["total_scores"] == 5

    def test_counts_rules_only(self, setup_db):
        conn = sqlite3.connect(setup_db)
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        conn.execute(
            "INSERT INTO scoring_stats (date, rules_only_count, llm_count) VALUES (?, ?, ?)",
            (today, 10, 5),
        )
        conn.execute(
            "INSERT INTO scoring_stats (date, rules_only_count, llm_count) VALUES (?, ?, ?)",
            (yesterday, 8, 3),
        )
        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)
        assert result["rules_only_count"] == 18

    def test_counts_cached_results(self, setup_db):
        conn = sqlite3.connect(setup_db)
        now = datetime.now()

        # Add cached results
        for i in range(3):
            scored_at = (now - timedelta(days=i)).isoformat()
            conn.execute(
                """INSERT INTO scores (input_type, content_hash, scored_at,
                   overall_score, dimensions_json, labels_json, summary, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", f"cached_{i}", scored_at, 70.0, "{}", "[]", "cached", "cache"),
            )

        # Add non-cached results
        for i in range(2):
            scored_at = (now - timedelta(days=i)).isoformat()
            conn.execute(
                """INSERT INTO scores (input_type, content_hash, scored_at,
                   overall_score, dimensions_json, labels_json, summary, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", f"llm_{i}", scored_at, 60.0, "{}", "[]", "llm", "deepseek"),
            )

        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)
        assert result["cached_count"] == 3
        assert result["total_scores"] == 5

    def test_token_usage_from_roi_table(self, setup_db):
        conn = sqlite3.connect(setup_db)
        now = datetime.now()

        # Add token_roi records
        for i in range(3):
            created_at = (now - timedelta(days=i)).isoformat()
            conn.execute(
                """INSERT INTO token_roi (content_hash, tokens_used, rules_score,
                   llm_score, roi, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"hash_{i}", 500, 50.0, 65.0, 0.03, created_at),
            )

        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)
        assert result["total_tokens_used"] == 1500


class TestCalculationCorrectness:
    """Test that savings calculations are correct."""

    def test_token_savings_percent_calculation(self, setup_db):
        conn = sqlite3.connect(setup_db)
        now = datetime.now()

        # Add 10 scores
        for i in range(10):
            scored_at = (now - timedelta(days=i % 10)).isoformat()
            conn.execute(
                """INSERT INTO scores (input_type, content_hash, scored_at,
                   overall_score, dimensions_json, labels_json, summary, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", f"hash_{i}", scored_at, 65.0, "{}", "[]", "test", "deepseek"),
            )

        # Add token usage: 5000 tokens total
        for i in range(5):
            created_at = (now - timedelta(days=i)).isoformat()
            conn.execute(
                """INSERT INTO token_roi (content_hash, tokens_used, rules_score,
                   llm_score, roi, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"roi_{i}", 1000, 50.0, 65.0, 0.015, created_at),
            )

        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)

        # 10 scores * 2000 tokens/naive = 20000 estimated
        # Actual: 5000 tokens
        # Savings: 15000 / 20000 = 75%
        assert result["estimated_tokens_if_no_optimization"] == 20000
        assert result["total_tokens_used"] == 5000
        assert result["token_savings_percent"] == 75.0

    def test_cost_savings_calculation(self, setup_db):
        conn = sqlite3.connect(setup_db)
        now = datetime.now()

        # 10 scores, 2000 tokens used
        for i in range(10):
            scored_at = (now - timedelta(days=1)).isoformat()
            conn.execute(
                """INSERT INTO scores (input_type, content_hash, scored_at,
                   overall_score, dimensions_json, labels_json, summary, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", f"hash_{i}", scored_at, 65.0, "{}", "[]", "test", "deepseek"),
            )

        created_at = (now - timedelta(days=1)).isoformat()
        conn.execute(
            """INSERT INTO token_roi (content_hash, tokens_used, rules_score,
               llm_score, roi, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("roi_0", 2000, 50.0, 65.0, 0.0075, created_at),
        )

        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)

        # Estimated: 10 * 2000 = 20000 tokens naive
        # Actual: 2000 tokens
        # Saved: 18000 tokens
        # Cost per 1K tokens: 0.001 yuan
        # Cost saved: 18000 / 1000 * 0.001 = 0.018 yuan
        assert result["estimated_cost_saved_yuan"] == 0.018

    def test_time_savings_calculation(self, setup_db):
        conn = sqlite3.connect(setup_db)
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()

        # 10 scores total
        for i in range(10):
            scored_at = (now - timedelta(days=1)).isoformat()
            conn.execute(
                """INSERT INTO scores (input_type, content_hash, scored_at,
                   overall_score, dimensions_json, labels_json, summary, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", f"hash_{i}", scored_at, 65.0, "{}", "[]", "test", "deepseek"),
            )

        # 7 rules_only, 3 llm
        conn.execute(
            "INSERT INTO scoring_stats (date, rules_only_count, llm_count) VALUES (?, ?, ?)",
            (today, 7, 3),
        )
        conn.commit()
        conn.close()

        result = get_savings_report(days=30, db_path=setup_db)

        # Manual: 10 * 5s = 50s
        # Our: 7 * 0.1s + 3 * 2.0s + 0 * 0.1s = 0.7 + 6.0 = 6.7s
        # Saved: 50 - 6.7 = 43.3s = 0.7 min
        assert result["estimated_time_if_manual"] == 50
        assert result["time_saved_minutes"] == 0.7

    def test_nonexistent_db_returns_zeros(self, tmp_path):
        """Test with a DB path that doesn't have the tables."""
        db_path = str(tmp_path / "nonexistent.db")
        result = get_savings_report(days=30, db_path=db_path)
        # Should return zeros without crashing
        assert result["total_scores"] == 0
