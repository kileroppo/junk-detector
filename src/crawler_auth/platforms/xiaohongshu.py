"""Xiaohongshu (Little Red Book) platform authentication."""
from __future__ import annotations

import httpx

from ..base import SignerHook
from ..browser_login import browser_login

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.xiaohongshu.com",
    "Referer": "https://www.xiaohongshu.com/",
}


class XiaohongshuAuth:
    """Xiaohongshu authentication with optional x-s/x-t signer support."""

    platform_name: str = "xiaohongshu"
    login_url: str = "https://www.xiaohongshu.com"
    cookie_domains: list[str] = ["xiaohongshu.com"]

    def __init__(self, signer_hook: SignerHook | None = None) -> None:
        self._signer_hook = signer_hook

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for Xiaohongshu login."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            wait_for_login_indicator="[class*=user], .reds-account-info",
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate cookies by checking Xiaohongshu page response."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {
            "User-Agent": _DEFAULT_HEADERS["User-Agent"],
            "Cookie": cookie_header,
        }
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(
                    "https://www.xiaohongshu.com/user/profile/me", headers=headers
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for Xiaohongshu requests."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        if self._signer_hook and url:
            sig_headers = self._signer_hook.sign(url, cookies)
            headers.update(sig_headers)
        return headers
