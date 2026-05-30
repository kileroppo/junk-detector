"""Weibo platform authentication (H5 / m.weibo.cn)."""
from __future__ import annotations

import httpx

from ..browser_login import browser_login

# H5 mobile UA — required for m.weibo.cn cookies to work
_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

_DEFAULT_HEADERS = {
    "User-Agent": _MOBILE_UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://m.weibo.cn/",
}


class WeiboAuth:
    """Weibo authentication using H5 (m.weibo.cn) cookies."""

    platform_name: str = "weibo"
    login_url: str = (
        "https://passport.weibo.cn/signin?entry=mweibo&r=https://m.weibo.cn/"
    )
    cookie_domains: list[str] = ["weibo.cn", "weibo.com", "sina.com.cn"]

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for Weibo H5 login."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            user_agent=_MOBILE_UA,
            post_login_urls=[
                "https://m.weibo.cn/",
                "https://m.weibo.cn/search?containerid=100103type%3D1%26q%3Dtest",
            ],
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate H5 cookies against m.weibo.cn."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get("https://m.weibo.cn/api/config", headers=headers)
                if resp.status_code != 200:
                    return False
                data = resp.json()
                return data.get("ok") == 1
        except httpx.HTTPError:
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for Weibo H5 requests."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {**_DEFAULT_HEADERS, "Cookie": cookie_header}
