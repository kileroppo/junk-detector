"""WeChat article search via Sogou.

Searches WeChat articles through Sogou's weixin search engine.
"""
from __future__ import annotations

import logging
import random
import time

import httpx
from bs4 import BeautifulSoup

from src.extractors.sources import MonitorItem

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class WechatSogouFetcher:
    """Search WeChat articles via Sogou search engine."""

    source_name: str = "wechat"
    _ENDPOINT = "https://weixin.sogou.com/weixin"
    _MIN_INTERVAL = 3.0  # Higher rate limit for Sogou

    def __init__(self, query: str = "热点") -> None:
        self._query = query
        self._last_fetch: float = 0

    async def fetch_items(self) -> list[MonitorItem]:
        """Fetch WeChat articles matching the query."""
        elapsed = time.time() - self._last_fetch
        if elapsed < self._MIN_INTERVAL:
            import asyncio
            await asyncio.sleep(self._MIN_INTERVAL - elapsed)

        try:
            headers = {
                "User-Agent": random.choice(_USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://weixin.sogou.com/",
            }
            params = {
                "type": "2",  # Article search
                "query": self._query,
            }

            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(self._ENDPOINT, headers=headers, params=params)
                resp.raise_for_status()

            self._last_fetch = time.time()

            soup = BeautifulSoup(resp.text, "html.parser")
            items: list[MonitorItem] = []

            # Parse search results
            results = soup.select(".news-list li") or soup.select(".txt-box")
            for result in results[:20]:
                link = result.select_one("a")
                if not link:
                    continue
                title = link.get_text(strip=True)
                url = link.get("href", "")
                if url and not url.startswith("http"):
                    url = f"https://weixin.sogou.com{url}"

                snippet_el = result.select_one(".txt-info") or result.select_one("p")
                snippet = snippet_el.get_text(strip=True)[:100] if snippet_el else ""

                if title:
                    items.append(MonitorItem(
                        title=title,
                        url=url,
                        source="wechat",
                        snippet=snippet,
                    ))
            return items

        except Exception as e:
            logger.warning("WeChat Sogou search failed: %s", e)
            return []
