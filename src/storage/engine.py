"""Unified SQLite connection factory."""

import os
import sqlite3


def get_db_path() -> str:
    """Get the database path from environment or default.

    Returns:
        Path to the SQLite database file.
    """
    return os.environ.get("JUNK_DETECTOR_DB", "junk_detector.db")


def get_db_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Create a thread-safe SQLite connection with row factory.

    Args:
        db_path: Optional path to the database file. If None, uses get_db_path().

    Returns:
        A configured sqlite3.Connection instance.
    """
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
