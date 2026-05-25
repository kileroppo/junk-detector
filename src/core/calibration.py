"""Scoring calibration module - tracks user feedback for continuous improvement."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from src.storage.db import _get_connection

_CREATE_FEEDBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    user_verdict TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_initialized_feedback_dbs: set[str] = set()

VALID_VERDICTS = ("junk", "ok", "excellent")


def _ensure_initialized(db_path: str) -> None:
    """Lazy initialization: create feedback table if not already done for this db_path."""
    if db_path not in _initialized_feedback_dbs:
        init_feedback_db(db_path)


def init_feedback_db(db_path: str = "junk_detector.db") -> None:
    """Create the feedback table if it does not exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_FEEDBACK_TABLE_SQL)
        conn.commit()
        _initialized_feedback_dbs.add(db_path)
    finally:
        conn.close()


def record_feedback(
    content_hash: str, user_verdict: str, db_path: str = "junk_detector.db"
) -> None:
    """Record user feedback on a scored piece of content.

    Args:
        content_hash: The SHA256 hash of the content text.
        user_verdict: One of 'junk', 'ok', 'excellent'.
        db_path: Path to the SQLite database file.

    Raises:
        ValueError: If user_verdict is not a valid verdict.
    """
    if user_verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid verdict '{user_verdict}'. Must be one of: {VALID_VERDICTS}")

    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO feedback (content_hash, user_verdict, created_at) VALUES (?, ?, ?)",
            (content_hash, user_verdict, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _score_to_verdict(score: float) -> str:
    """Map a numeric score to a verdict category.

    Args:
        score: Overall score from 0-100.

    Returns:
        'junk' if score < 40, 'ok' if 40-70, 'excellent' if > 70.
    """
    if score < 40:
        return "junk"
    elif score <= 70:
        return "ok"
    else:
        return "excellent"


def get_calibration_stats(db_path: str = "junk_detector.db") -> dict[str, Any]:
    """Calculate calibration statistics by comparing user feedback with scores.

    Joins the feedback table with the scores table on content_hash to compare
    predicted verdict (from overall_score) with user_verdict.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary with:
        - total_feedback_count: Total number of feedback entries with matching scores
        - agreement_rate: Percentage where predicted verdict matches user verdict
        - false_positives: Count of items scored as junk but user said ok/excellent
        - false_negatives: Count of items scored as ok/excellent but user said junk
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT f.user_verdict, s.overall_score
            FROM feedback f
            INNER JOIN scores s ON f.content_hash = s.content_hash
            """
        )
        rows = cursor.fetchall()

        total_count = len(rows)
        if total_count == 0:
            return {
                "total_feedback_count": 0,
                "agreement_rate": 0.0,
                "false_positives": 0,
                "false_negatives": 0,
            }

        agreements = 0
        false_positives = 0
        false_negatives = 0

        for row in rows:
            user_verdict = row["user_verdict"]
            predicted_verdict = _score_to_verdict(row["overall_score"])

            if predicted_verdict == user_verdict:
                agreements += 1
            elif predicted_verdict == "junk" and user_verdict in ("ok", "excellent"):
                false_positives += 1
            elif predicted_verdict in ("ok", "excellent") and user_verdict == "junk":
                false_negatives += 1

        agreement_rate = (agreements / total_count) * 100.0

        return {
            "total_feedback_count": total_count,
            "agreement_rate": agreement_rate,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        }
    finally:
        conn.close()


def suggest_rule_updates(db_path: str = "junk_detector.db") -> dict[str, list[str]]:
    """Analyze false negatives and false positives to suggest rule updates.

    False negatives: content user flagged as junk but we scored as ok/excellent.
    Extracts frequent Chinese character n-grams (2-4 chars) from false negative
    content that don't appear in true positive content.

    False positives: content we scored as junk but user said was ok/excellent.
    Suggests keywords from those items that may need removal.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary with:
        - suggested_keywords: List of frequent n-grams from false negatives
        - suggested_removals: List of frequent n-grams from false positives
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        # Get all feedback with score and content text
        cursor = conn.execute(
            """
            SELECT f.user_verdict, s.overall_score, s.title
            FROM feedback f
            INNER JOIN scores s ON f.content_hash = s.content_hash
            """
        )
        rows = cursor.fetchall()

        false_negative_texts: list[str] = []
        true_positive_texts: list[str] = []
        false_positive_texts: list[str] = []

        for row in rows:
            user_verdict = row["user_verdict"]
            predicted_verdict = _score_to_verdict(row["overall_score"])
            text = row["title"] or ""

            if predicted_verdict in ("ok", "excellent") and user_verdict == "junk":
                # False negative: we missed it, user says it's junk
                false_negative_texts.append(text)
            elif predicted_verdict == user_verdict and user_verdict != "junk":
                # True positive (content correctly identified as ok/excellent)
                true_positive_texts.append(text)
            elif predicted_verdict == "junk" and user_verdict in ("ok", "excellent"):
                # False positive: we said junk but user says it's fine
                false_positive_texts.append(text)

        suggested_keywords = _extract_distinctive_ngrams(false_negative_texts, true_positive_texts)
        suggested_removals = _extract_distinctive_ngrams(false_positive_texts, true_positive_texts)

        return {
            "suggested_keywords": suggested_keywords,
            "suggested_removals": suggested_removals,
        }
    finally:
        conn.close()


def _extract_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> list[str]:
    """Extract Chinese character n-grams from text.

    Args:
        text: Input text string.
        min_n: Minimum n-gram length.
        max_n: Maximum n-gram length.

    Returns:
        List of n-gram strings.
    """
    ngrams = []
    for n in range(min_n, max_n + 1):
        for i in range(len(text) - n + 1):
            ngram = text[i : i + n]
            # Only include n-grams that contain at least one CJK character
            if any("\u4e00" <= ch <= "\u9fff" for ch in ngram):
                ngrams.append(ngram)
    return ngrams


def _extract_distinctive_ngrams(
    target_texts: list[str],
    baseline_texts: list[str],
    top_k: int = 10,
    min_frequency: int = 2,
) -> list[str]:
    """Extract n-grams frequent in target texts but not in baseline texts.

    Args:
        target_texts: Texts to extract distinctive n-grams from.
        baseline_texts: Texts to compare against (exclude common n-grams).
        top_k: Maximum number of suggestions to return.
        min_frequency: Minimum occurrences in target to be considered.

    Returns:
        List of distinctive n-gram strings sorted by frequency.
    """
    if not target_texts:
        return []

    # Count n-grams in target texts
    target_counter: Counter[str] = Counter()
    for text in target_texts:
        ngrams = _extract_ngrams(text)
        target_counter.update(ngrams)

    # Count n-grams in baseline texts
    baseline_set: set[str] = set()
    for text in baseline_texts:
        ngrams = _extract_ngrams(text)
        baseline_set.update(ngrams)

    # Filter: must appear at least min_frequency times in target
    # and not appear in baseline
    distinctive = [
        (ngram, count)
        for ngram, count in target_counter.items()
        if count >= min_frequency and ngram not in baseline_set
    ]

    # Sort by frequency descending
    distinctive.sort(key=lambda x: x[1], reverse=True)

    return [ngram for ngram, _ in distinctive[:top_k]]
