"""SQLite storage layer for junk-detector scoring history."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from src.models.score import Content, ScoreResult

_CREATE_TABLE_SQL = """
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
);
"""

_ADD_EMBEDDING_COLUMN_SQL = """
ALTER TABLE scores ADD COLUMN embedding_json TEXT;
"""

_initialized_dbs: set[str] = set()


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a thread-safe SQLite connection with row factory."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_initialized(db_path: str) -> None:
    """Lazy initialization: create table if not already done for this db_path."""
    if db_path not in _initialized_dbs:
        init_db(db_path)


def init_db(db_path: str = "junk_detector.db") -> None:
    """Create the scores table if it does not exist.

    Also handles schema migration: adds embedding_json column to existing tables.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()

        # Migration: add embedding_json column if it doesn't exist (for existing DBs)
        cursor = conn.execute("PRAGMA table_info(scores)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "embedding_json" not in columns:
            conn.execute(_ADD_EMBEDDING_COLUMN_SQL)
            conn.commit()

        # Migration: add user_id column
        if "user_id" not in columns:
            conn.execute("ALTER TABLE scores ADD COLUMN user_id INTEGER;")
            conn.commit()

        # Migration: add cached_at column
        if "cached_at" not in columns:
            conn.execute("ALTER TABLE scores ADD COLUMN cached_at TEXT;")
            conn.commit()

        # Migration: add index on source_url
        conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_source_url ON scores(source_url)")
        conn.commit()

        _initialized_dbs.add(db_path)
    finally:
        conn.close()


def save(
    result: ScoreResult,
    content: Content,
    db_path: str = "junk_detector.db",
    embedding: list[float] | None = None,
    user_id: int | None = None,
) -> None:
    """Save a scoring result to the database.

    If a record with the same content_hash already exists, update it (upsert).

    Args:
        result: The ScoreResult from scoring.
        content: The Content that was scored.
        db_path: Path to the SQLite database file.
        embedding: Optional embedding vector to store alongside the score.
        user_id: Optional user ID for multi-tenant isolation.
    """
    _ensure_initialized(db_path)

    dimensions_json = json.dumps(result.dimensions.model_dump(), ensure_ascii=False)
    labels_json = json.dumps(result.labels, ensure_ascii=False)
    rule_hits_json = json.dumps(result.rule_hits, ensure_ascii=False)
    scored_at = result.scored_at.isoformat()
    embedding_json = json.dumps(embedding) if embedding else None

    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO scores (
                input_type, source_url, title, content_hash, scored_at,
                overall_score, dimensions_json, labels_json, summary,
                model_used, cost, rule_hits_json, confidence, embedding_json,
                user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_hash) DO UPDATE SET
                input_type = excluded.input_type,
                source_url = excluded.source_url,
                title = excluded.title,
                scored_at = excluded.scored_at,
                overall_score = excluded.overall_score,
                dimensions_json = excluded.dimensions_json,
                labels_json = excluded.labels_json,
                summary = excluded.summary,
                model_used = excluded.model_used,
                cost = excluded.cost,
                rule_hits_json = excluded.rule_hits_json,
                confidence = excluded.confidence,
                embedding_json = excluded.embedding_json
            """,
            (
                content.input_type.value,
                content.source_url,
                content.title,
                content.content_hash,
                scored_at,
                result.overall_score,
                dimensions_json,
                labels_json,
                result.summary,
                result.model_used,
                result.cost,
                rule_hits_json,
                result.confidence,
                embedding_json,
                user_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _build_filter_clause(filters: dict | None) -> tuple[str, list]:
    """Build a WHERE clause fragment from filter conditions.

    Supported filter keys:
        - min_score (float): overall_score >= value
        - max_score (float): overall_score <= value
        - label (str): labels_json LIKE '%label%'
        - date_from (str): scored_at >= value (ISO format)
        - date_to (str): scored_at <= value (ISO format)

    Args:
        filters: Optional dictionary of filter conditions.

    Returns:
        Tuple of (sql_fragment, params_list). The sql_fragment starts with
        " AND ..." if any filters are present, or is empty string if not.
    """
    sql = ""
    params: list = []

    if filters:
        if "min_score" in filters:
            sql += " AND overall_score >= ?"
            params.append(filters["min_score"])

        if "max_score" in filters:
            sql += " AND overall_score <= ?"
            params.append(filters["max_score"])

        if "label" in filters:
            sql += " AND labels_json LIKE ?"
            params.append(f"%{filters['label']}%")

        if "date_from" in filters:
            sql += " AND scored_at >= ?"
            params.append(filters["date_from"])

        if "date_to" in filters:
            sql += " AND scored_at <= ?"
            params.append(filters["date_to"])

        if "user_id" in filters:
            sql += " AND user_id = ?"
            params.append(filters["user_id"])

    return sql, params


def query(
    filters: dict | None = None,
    limit: int = 20,
    db_path: str = "junk_detector.db",
    offset: int = 0,
    user_id: int | None = None,
) -> list[dict]:
    """Query scoring history with optional filters.

    Supported filter keys:
        - min_score (float): overall_score >= value
        - max_score (float): overall_score <= value
        - label (str): labels_json LIKE '%label%'
        - date_from (str): scored_at >= value (ISO format)
        - date_to (str): scored_at <= value (ISO format)
        - user_id (int): filter by user_id

    Args:
        filters: Optional dictionary of filter conditions.
        limit: Maximum number of results to return.
        db_path: Path to the SQLite database file.
        offset: Number of rows to skip (for pagination).
        user_id: Optional user ID to filter results by owner.

    Returns:
        List of score records as dictionaries.
    """
    _ensure_initialized(db_path)

    if user_id is not None:
        if filters is None:
            filters = {}
        filters["user_id"] = user_id

    filter_clause, params = _build_filter_clause(filters)
    sql = "SELECT * FROM scores WHERE 1=1" + filter_clause
    sql += " ORDER BY scored_at DESC LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def count_records(
    filters: dict | None = None,
    db_path: str = "junk_detector.db",
) -> int:
    """Count total number of records matching the given filters.

    Args:
        filters: Optional dictionary of filter conditions (same as query()).
        db_path: Path to the SQLite database file.

    Returns:
        Total count of matching records.
    """
    _ensure_initialized(db_path)

    filter_clause, params = _build_filter_clause(filters)
    sql = "SELECT COUNT(*) FROM scores WHERE 1=1" + filter_clause

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_history(limit: int = 20, db_path: str = "junk_detector.db", user_id: int | None = None) -> list[dict]:
    """Shortcut to get recent scoring history.

    Args:
        limit: Maximum number of results to return.
        db_path: Path to the SQLite database file.
        user_id: Optional user ID to filter results by owner.

    Returns:
        List of recent score records as dictionaries.
    """
    return query(filters=None, limit=limit, db_path=db_path, user_id=user_id)


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a dictionary, deserializing JSON fields."""
    d = dict(row)
    # Deserialize JSON fields
    if d.get("dimensions_json"):
        d["dimensions"] = json.loads(d["dimensions_json"])
    if d.get("labels_json"):
        d["labels"] = json.loads(d["labels_json"])
    if d.get("rule_hits_json"):
        d["rule_hits"] = json.loads(d["rule_hits_json"])
    return d


def lookup_by_hash_prefix(hash_prefix: str, db_path: str = "junk_detector.db") -> dict | None:
    """Look up a single score record by content_hash prefix (LIKE query).

    Args:
        hash_prefix: A prefix of the content hash (at least 8 chars recommended).
        db_path: Path to the SQLite database file.

    Returns:
        A score record as a dictionary, or None if not found or multiple matches.
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT * FROM scores WHERE content_hash LIKE ?",
            (f"{hash_prefix}%",),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            return None
        return _row_to_dict(rows[0])
    finally:
        conn.close()


def query_by_content_hash(content_hash: str, db_path: str = "junk_detector.db") -> dict | None:
    """Query a single score record by its content_hash.

    Args:
        content_hash: The SHA256 hash of the content text.
        db_path: Path to the SQLite database file.

    Returns:
        A score record as a dictionary, or None if not found.
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM scores WHERE content_hash = ?", (content_hash,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def get_all_embeddings(db_path: str = "junk_detector.db") -> list[dict]:
    """Retrieve all rows that have a stored embedding vector.

    Used by the similarity detection system to brute-force compare
    a new article's embedding against all previously scored articles.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        List of dicts, each containing:
        - content_hash: Unique hash of the article
        - title: Article title
        - source_url: Article source URL
        - embedding: Deserialized embedding vector (list of floats)
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT content_hash, title, source_url, embedding_json
            FROM scores
            WHERE embedding_json IS NOT NULL
            """
        )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            try:
                embedding = json.loads(row["embedding_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            results.append(
                {
                    "content_hash": row["content_hash"],
                    "title": row["title"],
                    "source_url": row["source_url"],
                    "embedding": embedding,
                }
            )
        return results
    finally:
        conn.close()


def query_by_domain(domain: str, db_path: str = "junk_detector.db") -> list[float]:
    """Query overall_score values for all records matching a domain.

    Uses SQL LIKE to filter by domain in source_url, avoiding
    loading all rows into Python. Escapes SQL LIKE wildcards in the
    domain string to prevent wildcard injection.

    Args:
        domain: The domain to search for (e.g. "example.com").
        db_path: Path to the SQLite database file.

    Returns:
        List of overall_score floats for matching records.
    """
    _ensure_initialized(db_path)

    # Escape SQL LIKE special characters in the domain
    escaped_domain = domain.replace("%", "\\%").replace("_", "\\_")

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT overall_score FROM scores WHERE source_url LIKE ? ESCAPE '\\'",
            (f"%{escaped_domain}%",),
        )
        rows = cursor.fetchall()
        return [row["overall_score"] for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scoring stats tracking (rules_only vs LLM usage)
# ---------------------------------------------------------------------------

_CREATE_SCORING_STATS_SQL = """
CREATE TABLE IF NOT EXISTS scoring_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT UNIQUE NOT NULL,
    rules_only_count INTEGER DEFAULT 0,
    llm_count INTEGER DEFAULT 0
);
"""

_initialized_stats_dbs: set[str] = set()


def init_scoring_stats_table(db_path: str = "junk_detector.db") -> None:
    """Create the scoring_stats table if it does not exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    if db_path in _initialized_stats_dbs:
        return
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_SCORING_STATS_SQL)
        conn.commit()
        _initialized_stats_dbs.add(db_path)
    finally:
        conn.close()


def _ensure_stats_initialized(db_path: str) -> None:
    """Lazy initialization for scoring_stats table."""
    if db_path not in _initialized_stats_dbs:
        init_scoring_stats_table(db_path)


def increment_rules_only(db_path: str = "junk_detector.db") -> None:
    """Increment rules_only_count for today's date.

    Upserts the row for today, incrementing the counter by 1.

    Args:
        db_path: Path to the SQLite database file.
    """
    _ensure_stats_initialized(db_path)
    today = date.today().isoformat()
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO scoring_stats (date, rules_only_count, llm_count)
            VALUES (?, 1, 0)
            ON CONFLICT(date) DO UPDATE SET
                rules_only_count = rules_only_count + 1
            """,
            (today,),
        )
        conn.commit()
    finally:
        conn.close()


def increment_llm_count(db_path: str = "junk_detector.db") -> None:
    """Increment llm_count for today's date.

    Upserts the row for today, incrementing the counter by 1.

    Args:
        db_path: Path to the SQLite database file.
    """
    _ensure_stats_initialized(db_path)
    today = date.today().isoformat()
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO scoring_stats (date, rules_only_count, llm_count)
            VALUES (?, 0, 1)
            ON CONFLICT(date) DO UPDATE SET
                llm_count = llm_count + 1
            """,
            (today,),
        )
        conn.commit()
    finally:
        conn.close()


def get_daily_stats(db_path: str = "junk_detector.db", target_date: str | None = None) -> dict:
    """Get scoring stats for a given date.

    Args:
        db_path: Path to the SQLite database file.
        target_date: ISO date string (e.g. "2025-01-28"). Defaults to today.

    Returns:
        Dict with keys: rules_only_count, llm_count. Both default to 0 if no data.
    """
    _ensure_stats_initialized(db_path)
    if target_date is None:
        target_date = date.today().isoformat()
    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            "SELECT rules_only_count, llm_count FROM scoring_stats WHERE date = ?",
            (target_date,),
        )
        row = cursor.fetchone()
        if row is None:
            return {"rules_only_count": 0, "llm_count": 0}
        return {"rules_only_count": row["rules_only_count"], "llm_count": row["llm_count"]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scoring trends (daily aggregates)
# ---------------------------------------------------------------------------


def get_trends(days: int = 28, db_path: str = "junk_detector.db") -> list[dict]:
    """Get daily score aggregates for the last N days.

    Queries the scores table grouped by date (DATE(scored_at)) and returns
    average score, count, and junk count per day.

    Args:
        days: Number of days to look back (default 28).
        db_path: Path to the SQLite database file.

    Returns:
        List of dicts: [{date, avg_score, count, junk_count}] ordered by date asc.
    """
    _ensure_initialized(db_path)

    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT
                DATE(scored_at) as day,
                AVG(overall_score) as avg_score,
                COUNT(*) as count,
                SUM(CASE WHEN overall_score < 40 THEN 1 ELSE 0 END) as junk_count
            FROM scores
            WHERE DATE(scored_at) >= ?
            GROUP BY DATE(scored_at)
            ORDER BY day ASC
            """,
            (start_date,),
        )
        rows = cursor.fetchall()
        return [
            {
                "date": row["day"],
                "avg_score": round(row["avg_score"], 1),
                "count": row["count"],
                "junk_count": row["junk_count"],
            }
            for row in rows
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Feedback storage
# ---------------------------------------------------------------------------

_CREATE_FEEDBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score_id INTEGER,
    content_hash TEXT,
    user_verdict TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_initialized_feedback_dbs: set[str] = set()


def init_feedback_table(db_path: str = "junk_detector.db") -> None:
    """Create the feedback table if it does not exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    if db_path in _initialized_feedback_dbs:
        return
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_FEEDBACK_TABLE_SQL)
        conn.commit()
        _initialized_feedback_dbs.add(db_path)
    finally:
        conn.close()


def _ensure_feedback_initialized(db_path: str) -> None:
    """Lazy initialization for feedback table."""
    if db_path not in _initialized_feedback_dbs:
        init_feedback_table(db_path)


def save_feedback(
    score_id: int,
    content_hash: str,
    verdict: str,
    db_path: str = "junk_detector.db",
) -> None:
    """Save user feedback (wrong/correct) for a scoring result.

    Args:
        score_id: The ID of the score record.
        content_hash: The content hash of the scored item.
        verdict: User verdict - 'wrong' or 'correct'.
        db_path: Path to the SQLite database file.
    """
    _ensure_feedback_initialized(db_path)

    created_at = datetime.now().isoformat()
    conn = _get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO feedback (score_id, content_hash, user_verdict, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (score_id, content_hash, verdict, created_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_feedback_count(db_path: str = "junk_detector.db") -> int:
    """Get total number of feedback records.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Total count of feedback records.
    """
    _ensure_feedback_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM feedback")
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
