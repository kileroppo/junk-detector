"""Generic custom platform authentication."""
from __future__ import annotations

import re

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

_TEMPLATE_RE = re.compile(r"\{(\w+)\}")


def _resolve_templates(headers: dict[str, str], cookies: dict[str, str]) -> dict[str, str]:
    """Resolve {cookie_name} templates in header values."""
    resolved: dict[str, str] = {}
    for key, value in headers.items():
        def _replace(m: re.Match) -> str:
            return cookies.get(m.group(1), m.group(0))
        resolved[key] = _TEMPLATE_RE.sub(_replace, value)
    return resolved


class CustomPlatformAuth:
    """Authentication for user-defined custom platforms."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self.platform_name: str = config["id"]
        self.login_url: str = config["login_url"]
        self.cookie_domains: list[str] = list(config["cookie_domains"])

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Open browser for custom platform login."""
        return await browser_login(
            login_url=self.login_url,
            cookie_domains=self.cookie_domains,
            headless=headless,
            wait_for_login_indicator=None,
            timeout=60,
        )

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Validate cookies using validate_url if configured.

        Returns True if validated, False if validation fails.
        Raises ValueError if no validate_url is configured (caller should handle).
        """
        validate_url = self._config.get("validate_url")
        if not validate_url:
            raise ValueError("No validate_url configured for this platform")

        ua = self._config.get("user_agent") or _DEFAULT_HEADERS["User-Agent"]
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {
            **_DEFAULT_HEADERS,
            "User-Agent": ua,
            "Cookie": cookie_header,
        }
        extra = self._config.get("extra_headers") or {}
        if extra:
            headers.update(_resolve_templates(extra, cookies))

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(validate_url, headers=headers)
                # Consider 2xx as valid
                return 200 <= resp.status_code < 300
        except httpx.HTTPError:
            return False

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate headers for custom platform requests."""
        ua = self._config.get("user_agent") or _DEFAULT_HEADERS["User-Agent"]
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {
            **_DEFAULT_HEADERS,
            "User-Agent": ua,
            "Cookie": cookie_header,
        }
        extra = self._config.get("extra_headers") or {}
        if extra:
            headers.update(_resolve_templates(extra, cookies))
        return headers
