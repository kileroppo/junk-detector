"""SQLite implementation of StorageBackend."""
from __future__ import annotations

from src.models.score import Content, ScoreResult
from src.storage import db


class SQLiteBackend:
    """SQLite storage backend - delegates to existing db.py functions."""

    def __init__(self, db_path: str = "junk_detector.db") -> None:
        self._db_path = db_path
        db.init_db(db_path)

    def save(self, result: ScoreResult, content: Content, user_id: int | None = None) -> None:
        db.save(result, content, db_path=self._db_path, user_id=user_id)

    def query(self, filters: dict | None = None, limit: int = 20, user_id: int | None = None) -> list[dict]:
        return db.query(filters=filters, limit=limit, db_path=self._db_path, user_id=user_id)

    def get_history(self, limit: int = 20, user_id: int | None = None) -> list[dict]:
        return db.get_history(limit=limit, db_path=self._db_path, user_id=user_id)

    def query_by_content_hash(self, content_hash: str) -> dict | None:
        return db.query_by_content_hash(content_hash, db_path=self._db_path)
