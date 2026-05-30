"""Weibo Hot Search fetcher.

Fetches trending topics from Weibo's hot search API.
"""
from __future__ import annotations

import logging
import time

from src.extractors.sources import MonitorItem

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class WeiboHotFetcher:
    """Fetch hot search topics from Weibo."""

    source_name: str = "weibo"
    _ENDPOINT = "https://weibo.com/ajax/side/hotSearch"
    _MIN_INTERVAL = 2.0  # seconds between requests

    def __init__(self) -> None:
        self._last_fetch: float = 0

    async def fetch_items(self) -> list[MonitorItem]:
        """Fetch current Weibo hot search items."""
        # Rate limiting
        elapsed = time.time() - self._last_fetch
        if elapsed < self._MIN_INTERVAL:
            import asyncio
            await asyncio.sleep(self._MIN_INTERVAL - elapsed)

        try:
            import random
            headers = {
                "User-Agent": random.choice(_USER_AGENTS),
                "Accept": "application/json",
                "Referer": "https://weibo.com/",
            }

            from src.extractors.http_pool import get_client
            client = get_client()
            resp = await client.get(self._ENDPOINT, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            self._last_fetch = time.time()

            items: list[MonitorItem] = []
            realtime = data.get("data", {}).get("realtime", [])
            for entry in realtime[:30]:  # Top 30
                word = entry.get("word", "")
                if not word:
                    continue
                items.append(MonitorItem(
                    title=word,
                    url=f"https://s.weibo.com/weibo?q=%23{word}%23",
                    source="weibo",
                    snippet=entry.get("label_name", ""),
                ))
            return items

        except Exception as e:
            logger.warning("Weibo hot search fetch failed: %s", e)
            return []
