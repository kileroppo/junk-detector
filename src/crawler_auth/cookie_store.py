"""Persistent cookie storage with TTL-based expiry."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

_VALID_PLATFORM_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class CookieStore:
    """File-based cookie store with TTL expiry per platform."""

    def __init__(self, store_dir: Path | None = None) -> None:
        if store_dir is None:
            store_dir = Path.home() / ".crawler_auth" / "cookies"
        self._store_dir = store_dir
        self._store_dir.mkdir(parents=True, exist_ok=True)

    def _validate_platform(self, platform: str) -> None:
        """Validate platform name to prevent path traversal."""
        if not platform or not _VALID_PLATFORM_RE.match(platform):
            raise ValueError(
                f"Invalid platform name: {platform!r}. "
                "Only alphanumeric characters, dashes, and underscores are allowed."
            )

    def _path_for(self, platform: str) -> Path:
        self._validate_platform(platform)
        return self._store_dir / f"{platform}.json"

    def save(
        self, platform: str, cookies: dict[str, str], ttl_hours: int = 168
    ) -> None:
        """Save cookies for a platform with a TTL (default 7 days)."""
        data = {
            "cookies": cookies,
            "expires_at": time.time() + ttl_hours * 3600,
            "saved_at": time.time(),
        }
        path = self._path_for(platform)
        path.write_text(json.dumps(data, ensure_ascii=False))
        os.chmod(path, 0o600)

    def _read_file(self, platform: str) -> dict | None:
        path = self._path_for(platform)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def load(self, platform: str) -> dict[str, str] | None:
        """Load cookies for a platform, returning None if missing or expired."""
        data = self._read_file(platform)
        if data is None:
            return None
        if data.get("expires_at", 0) < time.time():
            return None
        return data.get("cookies")

    def load_unchecked(self, platform: str) -> dict[str, str] | None:
        """Load cookies ignoring expiry (useful when merging partial updates)."""
        data = self._read_file(platform)
        if data is None:
            return None
        return data.get("cookies")

    def update(
        self,
        platform: str,
        cookies: dict[str, str],
        *,
        merge: bool = True,
        ttl_hours: int = 168,
    ) -> dict[str, str]:
        """Save cookies, optionally merging with existing stored cookies."""
        if merge:
            existing = self.load_unchecked(platform) or {}
            cookies = {**existing, **cookies}
        self.save(platform, cookies, ttl_hours=ttl_hours)
        return cookies

    def is_expired(self, platform: str) -> bool:
        """Check if stored cookies for a platform have expired."""
        path = self._path_for(platform)
        if not path.exists():
            return True
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return True
        return data.get("expires_at", 0) < time.time()

    def clear(self, platform: str) -> None:
        """Remove stored cookies for a platform."""
        path = self._path_for(platform)
        if path.exists():
            path.unlink()

    def list_platforms(self) -> list[str]:
        """List all platforms with stored cookies."""
        return [p.stem for p in self._store_dir.glob("*.json")]
