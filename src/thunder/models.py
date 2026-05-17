"""Data models for Thunder stream monitoring."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FeedItem(BaseModel):
    """Represents a discovered content item from a source."""

    id: str = Field(default="", description="Auto-generated hash of the URL")
    url: str
    title: str | None = None
    source_name: str
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10, 1=highest")

    def model_post_init(self, __context) -> None:
        """Auto-generate id from url hash if not provided."""
        if not self.id:
            self.id = hashlib.sha256(self.url.encode()).hexdigest()[:16]

    @classmethod
    def from_rss_entry(cls, entry: dict, source_name: str) -> FeedItem:
        """Create a FeedItem from a feedparser entry dict.

        Args:
            entry: A dictionary from feedparser's feed.entries list.
            source_name: Name of the source this entry came from.

        Returns:
            A new FeedItem instance.
        """
        url = entry.get("link", entry.get("id", ""))
        title = entry.get("title")

        # Try to parse published date from the entry
        discovered_at = datetime.now(timezone.utc)
        if "published_parsed" in entry and entry["published_parsed"]:
            try:
                from time import mktime

                discovered_at = datetime.fromtimestamp(
                    mktime(entry["published_parsed"]), tz=timezone.utc
                )
            except (TypeError, ValueError, OverflowError):
                pass

        return cls(
            url=url,
            title=title,
            source_name=source_name,
            discovered_at=discovered_at,
        )


class SourceConfig(BaseModel):
    """Configuration for a content source."""

    name: str
    type: Literal["rss", "webhook"]
    url: str
    poll_interval_seconds: int = Field(default=300, ge=1)
    priority: int = Field(default=5, ge=1, le=10)
    enabled: bool = True
