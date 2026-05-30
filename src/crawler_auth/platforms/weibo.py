"""Weibo platform authentication."""
from __future__ import annotations

import httpx

from ..browser_login import browser_login

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class WeiboAuth:
    """Weibo authentication implementation."""

    platform_name: str = "weibo"
    login_url: str = "https://weibo.com/login.php"
    cookie_domains: list[str] = ["weibo.com", "sina.com.cn"]

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for Weibo login."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            wait_for_login_indicator=".gn_nav, [class*=ProfileHeader]",
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate cookies by checking if we can access Weibo logged in."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get("https://weibo.com/", headers=headers)
                # If redirected to login page, cookies are invalid
                if "login" in resp.url.path:
                    return False
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for Weibo requests."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {**_DEFAULT_HEADERS, "Cookie": cookie_header}
