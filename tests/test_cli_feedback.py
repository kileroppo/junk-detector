"""Tests for the CLI feedback command."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()


def _make_connection(db_path_actual):
    """Create a connection factory that sets row_factory."""

    def _factory(db_path):
        conn = sqlite3.connect(db_path_actual, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    return _factory


@pytest.fixture()
def mock_db(tmp_path, monkeypatch):
    """Set up an in-memory-like temp DB with a score record for testing."""
    db_file = str(tmp_path / "test_junk.db")

    # Create scores table and insert a test record
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
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
        """
    )
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
    conn.execute(
        """
        INSERT INTO scores (input_type, source_url, title, content_hash, scored_at,
                           overall_score, dimensions_json, labels_json, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "text",
            "http://example.com",
            "Test Article",
            "abcdef1234567890abcdef1234567890",
            "2025-01-01T00:00:00",
            35.0,
            "{}",
            "[]",
            "Test summary",
        ),
    )
    conn.commit()
    conn.close()

    # Patch the db_path used in the feedback command and calibration module
    monkeypatch.setattr("src.storage.db._initialized_dbs", set())
    monkeypatch.setattr("src.core.calibration._initialized_feedback_dbs", set())

    return db_file


class TestFeedbackRecording:
    """Test recording user feedback via CLI."""

    def test_record_feedback_success(self, mock_db, monkeypatch):
        """feedback --id <hash> --verdict junk records feedback successfully."""
        conn_factory = _make_connection(mock_db)
        with (
            patch(
                "src.storage.db._get_connection",
                side_effect=conn_factory,
            ),
            patch(
                "src.core.calibration._get_connection",
                side_effect=conn_factory,
            ),
        ):
            result = runner.invoke(app, ["feedback", "--id", "abcdef12", "--verdict", "junk"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Feedback recorded successfully" in result.output
        assert "Test Article" in result.output
        assert "junk" in result.output

    def test_record_feedback_excellent(self, mock_db):
        """feedback --id <hash> --verdict excellent records feedback."""
        conn_factory = _make_connection(mock_db)
        with (
            patch(
                "src.storage.db._get_connection",
                side_effect=conn_factory,
            ),
            patch(
                "src.core.calibration._get_connection",
                side_effect=conn_factory,
            ),
        ):
            result = runner.invoke(
                app, ["feedback", "--id", "abcdef1234567890", "--verdict", "excellent"]
            )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Feedback recorded successfully" in result.output
        assert "excellent" in result.output


class TestFeedbackStats:
    """Test displaying calibration stats."""

    def test_stats_display(self, mock_db):
        """feedback --stats shows calibration statistics table."""
        conn_factory = _make_connection(mock_db)
        with (
            patch(
                "src.core.calibration._get_connection",
                side_effect=conn_factory,
            ),
            patch(
                "src.storage.db._get_connection",
                side_effect=conn_factory,
            ),
        ):
            result = runner.invoke(app, ["feedback", "--stats"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Calibration Statistics" in result.output
        assert "Total Feedback" in result.output
        assert "Agreement Rate" in result.output
        assert "False Positives" in result.output
        assert "False Negatives" in result.output


class TestFeedbackSuggest:
    """Test displaying rule update suggestions."""

    def test_suggest_display(self, mock_db):
        """feedback --suggest shows suggestions or no-suggestions message."""
        conn_factory = _make_connection(mock_db)
        with (
            patch(
                "src.core.calibration._get_connection",
                side_effect=conn_factory,
            ),
            patch(
                "src.storage.db._get_connection",
                side_effect=conn_factory,
            ),
        ):
            result = runner.invoke(app, ["feedback", "--suggest"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Rule Update Suggestions" in result.output


class TestFeedbackErrors:
    """Test error handling for feedback command."""

    def test_invalid_verdict(self, mock_db):
        """feedback --id X --verdict invalid shows error."""
        conn_factory = _make_connection(mock_db)
        with patch(
            "src.storage.db._get_connection",
            side_effect=conn_factory,
        ):
            result = runner.invoke(app, ["feedback", "--id", "abcdef12", "--verdict", "bad"])

        assert result.exit_code == 1
        assert "invalid verdict" in result.output

    def test_missing_verdict_with_id(self):
        """feedback --id X without --verdict shows error."""
        result = runner.invoke(app, ["feedback", "--id", "abcdef12"])

        assert result.exit_code == 1
        assert "--verdict is required" in result.output

    def test_nonexistent_hash(self, mock_db):
        """feedback --id <nonexistent> --verdict ok shows error."""
        conn_factory = _make_connection(mock_db)
        with patch(
            "src.storage.db._get_connection",
            side_effect=conn_factory,
        ):
            result = runner.invoke(app, ["feedback", "--id", "zzzzzzzz", "--verdict", "ok"])

        assert result.exit_code == 1
        assert "no score found" in result.output

    def test_id_too_short(self):
        """feedback --id with less than 8 chars shows error."""
        result = runner.invoke(app, ["feedback", "--id", "abc", "--verdict", "junk"])

        assert result.exit_code == 1
        assert "at least 8 characters" in result.output

    def test_no_options(self):
        """feedback with no options shows error about --id."""
        result = runner.invoke(app, ["feedback"])

        assert result.exit_code == 1
        assert "--id is required" in result.output
