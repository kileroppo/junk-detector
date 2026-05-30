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

__all__ = [
    "AuthenticatedClient",
    "BrowserLogin",
    "CookieStore",
    "PlatformAuth",
    "SignerHook",
    "browser_login",
]

# Alias for backward compat with the BrowserLogin name in exports
BrowserLogin = browser_login
