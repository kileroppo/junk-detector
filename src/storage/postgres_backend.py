"""PostgreSQL implementation of StorageBackend (async)."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class PostgresBackend:
    """PostgreSQL storage backend using asyncpg.

    Note: Methods are async. When used with the sync API layer,
    they need to be wrapped with asyncio.run() or used in async context.
    """

    def __init__(self, dsn: str | None = None, **kwargs: Any) -> None:
        self._dsn = dsn
        self._pool = None
        self._kwargs = kwargs

    async def connect(self) -> None:
        """Initialize connection pool and ensure schema exists."""
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg is required for PostgreSQL backend. "
                "Install with: pip install junk-detector[postgres]"
            )
        self._pool = await asyncpg.create_pool(dsn=self._dsn, **self._kwargs)
        await self._ensure_schema()

    async def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scores (
                    id SERIAL PRIMARY KEY,
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
                    embedding_json TEXT,
                    user_id INTEGER,
                    cached_at TEXT
                )
            """)

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    async def save(self, result, content, user_id: int | None = None) -> None:
        """Save a scoring result to PostgreSQL."""
        if not self._pool:
            raise RuntimeError("PostgresBackend not connected. Call connect() first.")

        dimensions_json = json.dumps(result.dimensions.model_dump(), ensure_ascii=False)
        labels_json = json.dumps(result.labels, ensure_ascii=False)
        rule_hits_json = json.dumps(result.rule_hits, ensure_ascii=False)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO scores (
                    input_type, source_url, title, content_hash, scored_at,
                    overall_score, dimensions_json, labels_json, summary,
                    model_used, cost, rule_hits_json, confidence, user_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (content_hash) DO UPDATE SET
                    scored_at = EXCLUDED.scored_at,
                    overall_score = EXCLUDED.overall_score,
                    dimensions_json = EXCLUDED.dimensions_json,
                    labels_json = EXCLUDED.labels_json,
                    summary = EXCLUDED.summary,
                    model_used = EXCLUDED.model_used,
                    cost = EXCLUDED.cost,
                    rule_hits_json = EXCLUDED.rule_hits_json,
                    confidence = EXCLUDED.confidence
                WHERE scores.user_id IS NULL OR scores.user_id = $14
                """,
                content.input_type.value,
                content.source_url,
                content.title,
                content.content_hash,
                result.scored_at.isoformat(),
                result.overall_score,
                dimensions_json,
                labels_json,
                result.summary,
                result.model_used,
                result.cost,
                rule_hits_json,
                result.confidence,
                user_id,
            )

    async def query(
        self, filters: dict | None = None, limit: int = 20, user_id: int | None = None
    ) -> list[dict]:
        """Query scoring history."""
        if not self._pool:
            raise RuntimeError("PostgresBackend not connected. Call connect() first.")

        conditions = []
        params = []
        idx = 1

        if filters:
            if "min_score" in filters:
                conditions.append(f"overall_score >= ${idx}")
                params.append(filters["min_score"])
                idx += 1
            if "label" in filters:
                conditions.append(f"labels_json LIKE ${idx}")
                params.append(f"%{filters['label']}%")
                idx += 1

        if user_id is not None:
            conditions.append(f"user_id = ${idx}")
            params.append(user_id)
            idx += 1

        where = " AND ".join(conditions) if conditions else "TRUE"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM scores WHERE {where} ORDER BY scored_at DESC LIMIT ${idx}",
                *params,
            )
            return [dict(row) for row in rows]

    async def get_history(self, limit: int = 20, user_id: int | None = None) -> list[dict]:
        """Get recent scoring history."""
        return await self.query(filters=None, limit=limit, user_id=user_id)

    async def query_by_content_hash(self, content_hash: str) -> dict | None:
        """Look up a score by content hash."""
        if not self._pool:
            raise RuntimeError("PostgresBackend not connected. Call connect() first.")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM scores WHERE content_hash = $1", content_hash
            )
            return dict(row) if row else None
