"""Standalone multi-platform cookie authentication for web crawlers.

This module provides a reusable, protocol-based authentication system
for Chinese web platforms. It supports browser-based login via Playwright,
persistent cookie storage with TTL, and platform-specific header generation.

No dependencies on the rest of junk-detector.
"""
from __future__ import annotations

from .base import PlatformAuth, SignerHook
from .browser_login import browser_login
from .client import AuthenticatedClient
from .cookie_store import CookieStore
from .cookie_utils import parse_cookie_string, read_clipboard
from .custom_store import CustomPlatformStore
from .manager import (
    clear_platform_cookies,
    describe_platform,
    import_cookies,
    list_all_platform_statuses,
)
from .platform_meta import PLATFORM_META, get_platform_meta, list_platform_ids

__all__ = [
    "AuthenticatedClient",
    "CookieStore",
    "CustomPlatformStore",
    "PLATFORM_META",
    "PlatformAuth",
    "SignerHook",
    "browser_login",
    "clear_platform_cookies",
    "describe_platform",
    "get_platform_meta",
    "import_cookies",
    "list_all_platform_statuses",
    "list_platform_ids",
    "parse_cookie_string",
    "read_clipboard",
]
