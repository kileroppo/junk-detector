"""Token ROI tracking — measures value gained from LLM token spending."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

_CREATE_TOKEN_ROI_SQL = """
CREATE TABLE IF NOT EXISTS token_roi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT,
    tokens_used INTEGER,
    rules_score REAL,
    llm_score REAL,
    roi REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

_initialized_roi_dbs: set[str] = set()


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a thread-safe SQLite connection with row factory."""
    from src.storage.engine import get_db_connection

    return get_db_connection(db_path)


def _ensure_roi_table(db_path: str) -> None:
    """Create the token_roi table if it does not exist."""
    if db_path in _initialized_roi_dbs:
        return
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_TOKEN_ROI_SQL)
        conn.commit()
        _initialized_roi_dbs.add(db_path)
    finally:
        conn.close()


def compute_roi(rules_score: float, llm_score: float, tokens_used: int) -> float:
    """Compute ROI: information gain per token spent.

    ROI = abs(llm_score - rules_score) / max(tokens_used, 1)

    Higher ROI means the LLM provided more new information per token.

    Args:
        rules_score: The overall score from rules-only evaluation.
        llm_score: The overall score from LLM evaluation.
        tokens_used: Total tokens consumed by the LLM call.

    Returns:
        ROI value (float).
    """
    return abs(llm_score - rules_score) / max(tokens_used, 1)


def save_roi_record(
    content_hash: str,
    tokens_used: int,
    rules_score: float,
    llm_score: float,
    roi: float,
    db_path: str = "junk_detector.db",
) -> None:
    """Save an ROI record to the token_roi table.

    Args:
        content_hash: SHA256 hash of the content.
        tokens_used: Total tokens consumed.
        rules_score: Score from rules-only evaluation.
        llm_score: Score from LLM evaluation.
        roi: Computed ROI value.
        db_path: Path to the SQLite database file.
    """
    _ensure_roi_table(db_path)
    created_at = datetime.now().isoformat()
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO token_roi (content_hash, tokens_used, rules_score, llm_score, roi, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (content_hash, tokens_used, rules_score, llm_score, roi, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_roi_stats(db_path: str = "junk_detector.db") -> dict:
    """Get aggregate ROI statistics.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dict with keys: avg_roi, total_tokens, total_calls, avg_info_gain.
        Returns zeros if no data available.
    """
    _ensure_roi_table(db_path)
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                AVG(roi) as avg_roi,
                SUM(tokens_used) as total_tokens,
                COUNT(*) as total_calls,
                AVG(ABS(llm_score - rules_score)) as avg_info_gain
            FROM token_roi
            """
        )
        row = cursor.fetchone()
        if row is None or row["total_calls"] == 0:
            return {
                "avg_roi": 0.0,
                "total_tokens": 0,
                "total_calls": 0,
                "avg_info_gain": 0.0,
            }
        return {
            "avg_roi": round(row["avg_roi"] or 0.0, 6),
            "total_tokens": row["total_tokens"] or 0,
            "total_calls": row["total_calls"] or 0,
            "avg_info_gain": round(row["avg_info_gain"] or 0.0, 2),
        }
    finally:
        conn.close()
