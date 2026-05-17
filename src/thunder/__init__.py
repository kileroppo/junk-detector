"""Thunder — real-time content stream monitor.

Inspired by x-algorithm's Thunder service.
Polls content sources (RSS, Webhook) and discovers new items for scoring.
"""

from src.thunder.monitor import ThunderMonitor
from src.thunder.sources import ContentSource, RSSSource, WebhookSource
from src.thunder.models import FeedItem, SourceConfig

__all__ = [
    "ThunderMonitor",
    "ContentSource",
    "RSSSource",
    "WebhookSource",
    "FeedItem",
    "SourceConfig",
]
