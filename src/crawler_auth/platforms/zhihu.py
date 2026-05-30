"""Zhihu platform authentication."""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from ..base import SignerHook
from ..browser_login import browser_login

if TYPE_CHECKING:
    pass

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class ZhihuAuth:
    """Zhihu authentication with optional x-zse-96/x-zst-81 signer support."""

    platform_name: str = "zhihu"
    login_url: str = "https://www.zhihu.com/signin"
    cookie_domains: list[str] = ["zhihu.com"]

    def __init__(self, signer_hook: SignerHook | None = None) -> None:
        self._signer_hook = signer_hook

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for Zhihu login."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            wait_for_login_indicator=".AppHeader-profileAvatar, .TopstoryPage",
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate cookies by checking if Zhihu redirects to signin."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        try:
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=10.0
            ) as client:
                resp = await client.get("https://www.zhihu.com/", headers=headers)
                # If redirected to signin, cookies are invalid
                if resp.status_code in (301, 302):
                    location = resp.headers.get("location", "")
                    if "signin" in location:
                        return False
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for Zhihu requests."""
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {**_DEFAULT_HEADERS, "Cookie": cookie_header}
        if self._signer_hook and url:
            sig_headers = self._signer_hook.sign(url, cookies)
            headers.update(sig_headers)
        return headers
