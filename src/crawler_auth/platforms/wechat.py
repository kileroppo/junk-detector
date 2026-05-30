"""WeChat/Sogou platform authentication."""
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


class WechatAuth:
    """WeChat (via Sogou) authentication for reducing CAPTCHA blocks."""

    platform_name: str = "wechat"
    login_url: str = "https://weixin.sogou.com"
    cookie_domains: list[str] = ["sogou.com", "weixin.qq.com"]

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for WeChat/Sogou cookie capture."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            wait_for_login_indicator=None,
            timeout=60,
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate cookies by testing a search without CAPTCHA block."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(
                    "https://weixin.sogou.com/weixin?type=2&query=test",
                    headers=headers,
                )
                # CAPTCHA block usually returns a redirect or specific status
                if resp.status_code == 200 and "antispider" not in resp.text.lower():
                    return True
                return False
        except httpx.HTTPError:
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for WeChat/Sogou requests."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {**_DEFAULT_HEADERS, "Cookie": cookie_header}
