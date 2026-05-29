"""Abstract storage backend protocol for junk-detector."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.models.score import Content, ScoreResult


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for synchronous storage backends (SQLite, etc.)."""

    def save(self, result: ScoreResult, content: Content, user_id: int | None = None) -> None:
        """Save a scoring result."""
        ...

    def query(self, filters: dict | None = None, limit: int = 20, user_id: int | None = None) -> list[dict]:
        """Query scoring history with optional filters."""
        ...

    def get_history(self, limit: int = 20, user_id: int | None = None) -> list[dict]:
        """Get recent scoring history."""
        ...

    def query_by_content_hash(self, content_hash: str) -> dict | None:
        """Look up a score by content hash."""
        ...


@runtime_checkable
class AsyncStorageBackend(Protocol):
    """Protocol for async storage backends (PostgreSQL, etc.)."""

    async def save(self, result: ScoreResult, content: Content, user_id: int | None = None) -> None:
        """Save a scoring result."""
        ...

    async def query(self, filters: dict | None = None, limit: int = 20, user_id: int | None = None) -> list[dict]:
        """Query scoring history with optional filters."""
        ...

    async def get_history(self, limit: int = 20, user_id: int | None = None) -> list[dict]:
        """Get recent scoring history."""
        ...

    async def query_by_content_hash(self, content_hash: str) -> dict | None:
        """Look up a score by content hash."""
        ...
