"""Zhihu Hot List fetcher.

Fetches trending topics from Zhihu's hot list API.
"""
from __future__ import annotations

import logging
import time

from src.extractors.sources import MonitorItem

logger = logging.getLogger(__name__)


class ZhihuHotFetcher:
    """Fetch hot topics from Zhihu."""

    source_name: str = "zhihu"
    _ENDPOINT = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
    _MIN_INTERVAL = 2.0

    def __init__(self) -> None:
        self._last_fetch: float = 0

    async def fetch_items(self) -> list[MonitorItem]:
        """Fetch current Zhihu hot list items."""
        elapsed = time.time() - self._last_fetch
        if elapsed < self._MIN_INTERVAL:
            import asyncio
            await asyncio.sleep(self._MIN_INTERVAL - elapsed)

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Referer": "https://www.zhihu.com/hot",
            }

            from src.extractors.http_pool import get_client
            client = get_client()
            resp = await client.get(self._ENDPOINT, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            self._last_fetch = time.time()

            items: list[MonitorItem] = []
            for entry in data.get("data", [])[:30]:
                target = entry.get("target", {})
                title = target.get("title", "")
                if not title:
                    continue
                url = target.get("url", "")
                # Zhihu API returns internal URLs, convert to web URL
                question_id = target.get("id", "")
                if question_id and not url.startswith("http"):
                    url = f"https://www.zhihu.com/question/{question_id}"
                snippet = target.get("excerpt", "")
                items.append(MonitorItem(
                    title=title,
                    url=url,
                    source="zhihu",
                    snippet=snippet[:100] if snippet else "",
                ))
            return items

        except Exception as e:
            logger.warning("Zhihu hot list fetch failed: %s", e)
            return []
