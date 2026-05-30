"""Bilibili platform authentication."""
from __future__ import annotations

import httpx

from ..browser_login import browser_login

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.bilibili.com/",
}


class BilibiliAuth:
    """Bilibili authentication with CSRF token extraction."""

    platform_name: str = "bilibili"
    login_url: str = "https://passport.bilibili.com/login"
    cookie_domains: list[str] = ["bilibili.com"]

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for Bilibili login."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            wait_for_login_indicator=".header-avatar-wrap, .bili-avatar",
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate cookies by checking the Bilibili nav API."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.bilibili.com/x/web-interface/nav",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # code 0 means logged in
                    return data.get("code") == 0
                return False
        except (httpx.HTTPError, ValueError):
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for Bilibili requests, including CSRF token."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        # Extract CSRF token from bili_jct cookie for POST requests
        csrf = cookies.get("bili_jct", "")
        if csrf:
            headers["x-csrf-token"] = csrf
        return headers
