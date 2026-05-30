"""Base protocols for the crawler_auth module."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SignerHook(Protocol):
    """Protocol for pluggable signature algorithms.

    Platforms like Zhihu (x-zse-96) and Xiaohongshu (x-s) require
    custom request signing. Implement this protocol to inject signatures.
    """

    def sign(self, url: str, cookies: dict[str, str]) -> dict[str, str]:
        """Generate signature headers for the given URL and cookies.

        Returns a dict of header name -> header value to merge into the request.
        """
        ...


@runtime_checkable
class PlatformAuth(Protocol):
    """Protocol for platform-specific authentication.

    Each platform provides login flow metadata and cookie validation.
    """

    @property
    def platform_name(self) -> str:
        """Unique name identifying this platform (e.g. 'zhihu')."""
        ...

    @property
    def login_url(self) -> str:
        """URL where the user logs in via browser."""
        ...

    @property
    def cookie_domains(self) -> list[str]:
        """Domains to capture cookies from after login."""
        ...

    async def login(self, headless: bool = False) -> dict[str, str]:
        """Perform browser-based login, return extracted cookies."""
        ...

    async def validate_cookies(self, cookies: dict[str, str]) -> bool:
        """Check if the given cookies are still valid for this platform."""
        ...

    def get_headers(self, cookies: dict[str, str], url: str = "") -> dict[str, str]:
        """Generate request headers including cookies and optional signatures."""
        ...
