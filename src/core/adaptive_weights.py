"""Adaptive feedback weights - learns from user feedback to adjust scoring.

When a user marks a score as 'wrong', the system adjusts dimension weights
based on which dimensions dominated the score. Over time, this personalizes
scoring to match the user's judgment.
"""

from __future__ import annotations

from datetime import datetime

from src.storage.db import _get_connection

# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

_CREATE_WEIGHT_ADJUSTMENTS_SQL = """
CREATE TABLE IF NOT EXISTS weight_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'anonymous',
    dimension TEXT NOT NULL,
    adjustment REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);
"""

_initialized_weight_dbs: set[str] = set()


def init_weight_adjustments_table(db_path: str = "junk_detector.db") -> None:
    """Create the weight_adjustments table if it does not exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    if db_path in _initialized_weight_dbs:
        return
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_WEIGHT_ADJUSTMENTS_SQL)
        conn.commit()
        _initialized_weight_dbs.add(db_path)
    finally:
        conn.close()


def _ensure_weight_initialized(db_path: str) -> None:
    """Lazy initialization for weight_adjustments table."""
    if db_path not in _initialized_weight_dbs:
        init_weight_adjustments_table(db_path)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def save_weight_adjustment(
    user_id: str,
    dimension: str,
    adjustment: float,
    db_path: str = "junk_detector.db",
) -> None:
    """Save or update a weight adjustment for a user/dimension pair.

    Uses upsert logic: if a row exists for the user+dimension, updates it
    by adding the new adjustment to the existing value.

    Args:
        user_id: User identifier (defaults to 'anonymous').
        dimension: The scoring dimension name.
        adjustment: The adjustment delta to apply.
        db_path: Path to the SQLite database file.
    """
    _ensure_weight_initialized(db_path)

    updated_at = datetime.now().isoformat()
    conn = _get_connection(db_path)
    try:
        # Check if row exists
        cursor = conn.execute(
            "SELECT id, adjustment FROM weight_adjustments WHERE user_id = ? AND dimension = ?",
            (user_id, dimension),
        )
        row = cursor.fetchone()

        if row:
            new_adjustment = row["adjustment"] + adjustment
            # Clamp cumulative adjustment to [-1.0, +1.0] to prevent unbounded drift
            new_adjustment = max(-1.0, min(1.0, new_adjustment))
            conn.execute(
                "UPDATE weight_adjustments SET adjustment = ?, updated_at = ? WHERE id = ?",
                (new_adjustment, updated_at, row["id"]),
            )
        else:
            # Clamp even the initial adjustment
            clamped_adjustment = max(-1.0, min(1.0, adjustment))
            conn.execute(
                """
                INSERT INTO weight_adjustments (user_id, dimension, adjustment, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, dimension, clamped_adjustment, updated_at),
            )
        conn.commit()
    finally:
        conn.close()


def get_adjusted_weights(
    user_id: str = "anonymous",
    base_weights: dict[str, float] | None = None,
    db_path: str = "junk_detector.db",
) -> dict[str, float]:
    """Get scoring weights adjusted by accumulated user feedback.

    Applies stored adjustments on top of base weights to produce
    personalized scoring weights for the user.

    Args:
        user_id: User identifier.
        base_weights: Base dimension weights. Uses defaults if None.
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary of dimension -> adjusted weight.
    """
    _ensure_weight_initialized(db_path)

    if base_weights is None:
        base_weights = {
            "originality": 1.0,
            "info_density": 1.0,
            "reasoning_quality": 1.0,
            "readability": 0.8,
            "timeliness": 0.6,
            "ai_generated_prob": -0.8,
            "emotional_manipulation": -1.0,
            "advertorial_prob": -1.0,
            "scam_prob": -1.2,
        }

    # Get adjustments from DB
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT dimension, adjustment FROM weight_adjustments WHERE user_id = ?",
            (user_id,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    # Apply adjustments
    adjusted = dict(base_weights)
    for row in rows:
        dim = row["dimension"]
        if dim in adjusted:
            adjusted[dim] = adjusted[dim] + row["adjustment"]

    return adjusted


def compute_feedback_adjustments(
    verdict: str,
    overall_score: float,
    dimensions: dict[str, float],
) -> dict[str, float]:
    """Compute weight adjustments based on user feedback.

    Logic:
    - If verdict is 'wrong' and score was HIGH (>60): user thinks content is junk,
      so increase negative dimension weights (make them more negative) by 0.05
      for negative dimensions that scored low (didn't catch it).
    - If verdict is 'wrong' and score was LOW (<40): user thinks content is good,
      so decrease negative dimension weights by 0.05 (make them less harsh).
    - If verdict is 'correct': no adjustment needed.

    Args:
        verdict: User feedback - 'wrong' or 'correct'.
        overall_score: The overall score that was given.
        dimensions: The dimension scores dict.

    Returns:
        Dictionary of dimension -> adjustment delta.
    """
    if verdict != "wrong":
        return {}

    adjustments: dict[str, float] = {}
    step = 0.05

    negative_dims = ["ai_generated_prob", "emotional_manipulation", "advertorial_prob", "scam_prob"]
    positive_dims = ["originality", "info_density", "reasoning_quality", "readability", "timeliness"]

    if overall_score > 60:
        # Score was too high, user says it should be junk.
        # Negative dimensions should have caught it - increase their weight magnitude.
        for dim in negative_dims:
            dim_score = dimensions.get(dim, 0)
            if dim_score < 50:
                # This dimension was low (didn't flag it) - make weight more negative
                adjustments[dim] = -step
        # Also slightly reduce positive dimension weights
        for dim in positive_dims:
            dim_score = dimensions.get(dim, 50)
            if dim_score > 60:
                adjustments[dim] = -step
    elif overall_score < 40:
        # Score was too low, user says it's actually good.
        # Negative dimensions were too harsh - reduce their weight magnitude.
        for dim in negative_dims:
            dim_score = dimensions.get(dim, 0)
            if dim_score > 50:
                # This dimension was high (over-flagged) - make weight less negative
                adjustments[dim] = step
        # Also slightly increase positive dimension weights
        for dim in positive_dims:
            dim_score = dimensions.get(dim, 50)
            if dim_score < 40:
                adjustments[dim] = step

    return adjustments
