"""Tests for storage backend protocol, SQLite backend, and factory."""
from __future__ import annotations

import pytest

from src.storage.backend import AsyncStorageBackend, StorageBackend
from src.storage.sqlite_backend import SQLiteBackend
from src.storage.factory import get_storage_backend
from src.models.score import Content, DimensionScores, InputType, ScoreResult


class TestStorageBackendProtocol:
    def test_sqlite_backend_implements_protocol(self):
        backend = SQLiteBackend(db_path=":memory:")
        assert isinstance(backend, StorageBackend)

    def test_postgres_backend_has_async_interface(self):
        """PostgresBackend methods are coroutine functions (async)."""
        import asyncio
        from src.storage.postgres_backend import PostgresBackend

        backend = PostgresBackend(dsn="postgresql://localhost/test")
        assert asyncio.iscoroutinefunction(backend.save)
        assert asyncio.iscoroutinefunction(backend.query)
        assert asyncio.iscoroutinefunction(backend.get_history)
        assert asyncio.iscoroutinefunction(backend.query_by_content_hash)

    def test_sqlite_backend_has_sync_interface(self):
        """SQLiteBackend methods are regular functions (not async)."""
        import asyncio

        backend = SQLiteBackend(db_path=":memory:")
        assert not asyncio.iscoroutinefunction(backend.save)
        assert not asyncio.iscoroutinefunction(backend.query)
        assert not asyncio.iscoroutinefunction(backend.get_history)
        assert not asyncio.iscoroutinefunction(backend.query_by_content_hash)

    def test_async_protocol_exists(self):
        """AsyncStorageBackend protocol is importable and runtime_checkable."""
        assert hasattr(AsyncStorageBackend, 'save')
        assert hasattr(AsyncStorageBackend, 'query')
        assert hasattr(AsyncStorageBackend, 'get_history')
        assert hasattr(AsyncStorageBackend, 'query_by_content_hash')


class TestSQLiteBackend:
    def test_save_and_query(self, tmp_db_path):
        backend = SQLiteBackend(db_path=tmp_db_path)
        result = ScoreResult(
            overall_score=75.0,
            dimensions=DimensionScores(
                originality=80,
                info_density=70,
                reasoning_quality=75,
                readability=80,
                timeliness=60,
                ai_generated_prob=10,
                emotional_manipulation=5,
                advertorial_prob=10,
                scam_prob=5,
            ),
            labels=[],
            summary="test",
            confidence=0.9,
            model_used="test",
        )
        content = Content(input_type=InputType.TEXT, text="test content", content_hash="")
        content.compute_hash()

        backend.save(result, content, user_id=1)
        rows = backend.query(user_id=1)
        assert len(rows) == 1
        assert rows[0]["overall_score"] == 75.0

    def test_query_by_content_hash(self, tmp_db_path):
        backend = SQLiteBackend(db_path=tmp_db_path)
        result = ScoreResult(
            overall_score=60.0,
            dimensions=DimensionScores(
                originality=60,
                info_density=60,
                reasoning_quality=60,
                readability=60,
                timeliness=60,
                ai_generated_prob=30,
                emotional_manipulation=20,
                advertorial_prob=20,
                scam_prob=10,
            ),
            labels=[],
            summary="test",
            confidence=0.8,
            model_used="test",
        )
        content = Content(input_type=InputType.TEXT, text="hash test", content_hash="")
        content.compute_hash()

        backend.save(result, content)
        found = backend.query_by_content_hash(content.content_hash)
        assert found is not None
        assert found["overall_score"] == 60.0


class TestFactory:
    def test_default_returns_sqlite(self):
        backend = get_storage_backend({"backend": "sqlite", "sqlite": {"path": ":memory:"}})
        assert isinstance(backend, SQLiteBackend)

    def test_postgres_config_returns_postgres_backend(self):
        from src.storage.postgres_backend import PostgresBackend

        backend = get_storage_backend(
            {
                "backend": "postgres",
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "dbname": "test",
                    "user": "test",
                    "password": "test",
                },
            }
        )
        assert isinstance(backend, PostgresBackend)

    def test_empty_config_defaults_to_sqlite(self):
        backend = get_storage_backend({})
        assert isinstance(backend, SQLiteBackend)
