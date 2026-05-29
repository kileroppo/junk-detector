"""Chinese content source fetchers for active monitoring.

Provides a common interface for fetching hot/trending content
from Chinese platforms (Weibo, Zhihu, WeChat).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class MonitorItem:
    """A single item fetched from a content source."""
    title: str
    url: str
    source: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    snippet: str = ""


@runtime_checkable
class SourceFetcher(Protocol):
    """Protocol for content source fetchers."""

    source_name: str

    async def fetch_items(self) -> list[MonitorItem]:
        """Fetch trending/hot items from the source."""
        ...
