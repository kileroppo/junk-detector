"""Authenticated HTTP client factory for crawler requests."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .base import PlatformAuth
from .cookie_store import CookieStore
from .platforms import PLATFORMS

# Domain to platform mapping for auto-detection
_DOMAIN_MAP: dict[str, str] = {
    "zhihu.com": "zhihu",
    "weibo.com": "weibo",
    "weibo.cn": "weibo",
    "sina.com.cn": "weibo",
    "xiaohongshu.com": "xiaohongshu",
    "xhslink.com": "xiaohongshu",
    "sogou.com": "wechat",
    "weixin.qq.com": "wechat",
    "bilibili.com": "bilibili",
    "b23.tv": "bilibili",
}


class AuthenticatedClient:
    """High-level client that auto-detects platforms and applies auth."""

    def __init__(
        self,
        cookie_store: CookieStore | None = None,
        platforms: dict[str, PlatformAuth] | None = None,
    ) -> None:
        self._cookie_store = cookie_store or CookieStore()
        if platforms is not None:
            self._platforms = platforms
            self._platform_registry = None
        else:
            # Store the registry for lazy instantiation
            self._platforms: dict[str, PlatformAuth] = {}
            self._platform_registry = PLATFORMS

    def _get_platform(self, name: str) -> PlatformAuth | None:
        """Get a platform instance, lazily instantiating if needed."""
        if name in self._platforms:
            return self._platforms[name]
        if self._platform_registry and name in self._platform_registry:
            self._platforms[name] = self._platform_registry[name]()
            return self._platforms[name]
        return None

    @property
    def cookie_store(self) -> CookieStore:
        """Access the underlying cookie store."""
        return self._cookie_store

    def detect_platform(self, url: str) -> str | None:
        """Detect which platform a URL belongs to.

        Returns the platform name or None if not recognized.
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        # Check exact domain match first
        if host in _DOMAIN_MAP:
            return _DOMAIN_MAP[host]
        # Check if host ends with any known domain
        for domain, platform in _DOMAIN_MAP.items():
            if host.endswith("." + domain) or host == domain:
                return platform
        return None

    def get_client(
        self, platform: str, url: str = ""
    ) -> httpx.AsyncClient:
        """Create a configured httpx.AsyncClient with auth headers for a platform.

        Args:
            platform: Platform name (e.g. 'zhihu').
            url: Optional URL to generate platform-specific signatures.

        Returns:
            Configured httpx.AsyncClient with cookies/headers applied.
        """
        cookies = self._cookie_store.load(platform) or {}
        auth_impl = self._get_platform(platform)
        headers = {}
        if auth_impl:
            headers = auth_impl.get_headers(cookies, url)
        return httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=15.0,
        )

    async def fetch(self, url: str, platform: str | None = None) -> httpx.Response:
        """Fetch a URL with automatic platform detection and auth.

        Args:
            url: The URL to fetch.
            platform: Optional platform override (auto-detected if None).

        Returns:
            httpx.Response from the request.
        """
        if platform is None:
            platform = self.detect_platform(url)

        if platform and self._get_platform(platform):
            async with self.get_client(platform, url) as client:
                return await client.get(url)
        else:
            # Fallback: plain request without auth
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=15.0
            ) as client:
                return await client.get(url)

    async def ensure_login(self, platform: str, headless: bool = False) -> None:
        """Ensure valid cookies exist for a platform, triggering login if needed.

        Args:
            platform: Platform name to authenticate.
            headless: Whether to run the browser headless.
        """
        # Check if we already have valid cookies
        if not self._cookie_store.is_expired(platform):
            cookies = self._cookie_store.load(platform)
            if cookies:
                auth_impl = self._get_platform(platform)
                if auth_impl:
                    is_valid = await auth_impl.validate_cookies(cookies)
                    if is_valid:
                        return

        # Need to login
        auth_impl = self._get_platform(platform)
        if auth_impl is None:
            raise ValueError(f"Unknown platform: {platform}")
        cookies = await auth_impl.login(headless=headless)
        self._cookie_store.save(platform, cookies)
