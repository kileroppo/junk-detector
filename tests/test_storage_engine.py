"""Tests for src/storage/engine.py — unified SQLite connection factory."""

from __future__ import annotations

import sqlite3

import pytest

from src.storage.engine import get_db_connection, get_db_path


class TestGetDbPath:
    """Tests for get_db_path()."""

    def test_default_path(self, monkeypatch):
        """get_db_path returns default when env var not set."""
        monkeypatch.delenv("JUNK_DETECTOR_DB", raising=False)
        assert get_db_path() == "junk_detector.db"

    def test_custom_path_from_env(self, monkeypatch):
        """get_db_path reads JUNK_DETECTOR_DB environment variable."""
        monkeypatch.setenv("JUNK_DETECTOR_DB", "/tmp/custom.db")
        assert get_db_path() == "/tmp/custom.db"


class TestGetDbConnection:
    """Tests for get_db_connection()."""

    def test_returns_connection(self, tmp_path):
        """get_db_connection returns a sqlite3.Connection."""
        db_path = str(tmp_path / "test.db")
        conn = get_db_connection(db_path)
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()

    def test_row_factory_set(self, tmp_path):
        """get_db_connection sets row_factory to sqlite3.Row."""
        db_path = str(tmp_path / "test.db")
        conn = get_db_connection(db_path)
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_uses_default_path_when_none(self, monkeypatch, tmp_path):
        """get_db_connection uses get_db_path() when db_path is None."""
        db_file = str(tmp_path / "env_test.db")
        monkeypatch.setenv("JUNK_DETECTOR_DB", db_file)
        conn = get_db_connection(None)
        try:
            assert isinstance(conn, sqlite3.Connection)
            # Verify we can write to the expected path
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.commit()
        finally:
            conn.close()

        # Verify file was created at the env-specified path
        import os
        assert os.path.exists(db_file)
