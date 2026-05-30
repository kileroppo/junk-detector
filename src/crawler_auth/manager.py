"""High-level cookie management for CLI and Web UI."""
from __future__ import annotations

import time
from datetime import datetime

from .cookie_store import CookieStore
from .cookie_utils import parse_cookie_string
from .platform_meta import get_platform_meta, list_platform_ids
from .platforms import PLATFORMS


def _format_ts(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def describe_platform(store: CookieStore, platform_id: str) -> dict:
    """Build status summary for one platform."""
    meta = get_platform_meta(platform_id)
    data = store._read_file(platform_id)
    now = time.time()

    if data is None:
        return {
            **meta,
            "status": "missing",
            "cookie_count": 0,
            "cookie_keys": [],
            "expires_at": None,
            "expires_at_label": None,
            "saved_at_label": None,
        }

    cookies = data.get("cookies") or {}
    expires_at = float(data.get("expires_at") or 0)
    saved_at = float(data.get("saved_at") or 0)
    expired = expires_at < now

    if expired:
        status = "expired"
    elif cookies:
        status = "active"
    else:
        status = "missing"

    return {
        **meta,
        "status": status,
        "cookie_count": len(cookies),
        "cookie_keys": sorted(cookies.keys()),
        "expires_at": expires_at if expires_at else None,
        "expires_at_label": _format_ts(expires_at),
        "saved_at_label": _format_ts(saved_at),
    }


def list_all_platform_statuses(store: CookieStore | None = None) -> list[dict]:
    """List status for every registered platform."""
    store = store or CookieStore()
    return [describe_platform(store, pid) for pid in list_platform_ids()]


def import_cookies(
    platform_id: str,
    raw: str,
    *,
    merge: bool = True,
    store: CookieStore | None = None,
) -> dict:
    """Parse and save cookies for a platform."""
    if platform_id not in PLATFORMS:
        raise ValueError(f"Unknown platform: {platform_id}")
    parsed = parse_cookie_string(raw)
    store = store or CookieStore()
    merged = store.update(platform_id, parsed, merge=merge)
    return {
        "imported_keys": sorted(parsed.keys()),
        "total_count": len(merged),
        "platform": describe_platform(store, platform_id),
    }


def clear_platform_cookies(
    platform_id: str, store: CookieStore | None = None
) -> dict:
    """Remove stored cookies for a platform."""
    if platform_id not in PLATFORMS:
        raise ValueError(f"Unknown platform: {platform_id}")
    store = store or CookieStore()
    store.clear(platform_id)
    return {"platform": describe_platform(store, platform_id)}
