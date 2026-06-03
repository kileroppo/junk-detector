"""Persistent storage for user-defined custom platform configurations."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_DEFAULT_CONFIG: list[dict] = []


class CustomPlatformStore:
    """File-based store for custom platform definitions.

    Each platform entry::

        {
            "id": "douban",
            "label": "豆瓣",
            "domains": ["douban.com"],
            "login_url": "https://www.douban.com/accounts/login",
            "cookie_domains": ["douban.com"],
            "key_cookies": ["bid", "dbcl2"],
            "validate_url": "https://www.douban.com/mine/",
            "extra_headers": {"x-csrf-token": "{cookie_name}"},
            "user_agent": null
        }
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            config_path = Path.home() / ".crawler_auth" / "custom_platforms.json"
        self._path = Path(config_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _validate_id(self, platform_id: str) -> None:
        if not platform_id or not _VALID_ID_RE.match(platform_id):
            raise ValueError(
                f"Invalid platform ID: {platform_id!r}. "
                "Only alphanumeric characters, dashes, and underscores are allowed."
            )

    def _read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_all(self, platforms: list[dict]) -> None:
        self._path.write_text(json.dumps(platforms, ensure_ascii=False, indent=2))
        os.chmod(self._path, 0o600)

    def list_all(self) -> list[dict]:
        """Return all custom platform configs."""
        return self._read_all()

    def get(self, platform_id: str) -> dict | None:
        """Return a single custom platform config by ID."""
        self._validate_id(platform_id)
        for p in self._read_all():
            if p.get("id") == platform_id:
                return p
        return None

    def save(self, config: dict) -> dict:
        """Create or update a custom platform config.

        Required keys: id, label, domains, login_url, cookie_domains.
        Optional keys: key_cookies, validate_url, extra_headers, user_agent.
        """
        platform_id = config.get("id", "")
        self._validate_id(platform_id)

        required = ["id", "label", "domains", "login_url", "cookie_domains"]
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        platforms = self._read_all()
        entry = {
            "id": platform_id,
            "label": config["label"],
            "domains": list(config["domains"]),
            "login_url": config["login_url"],
            "cookie_domains": list(config["cookie_domains"]),
            "key_cookies": list(config.get("key_cookies") or []),
            "validate_url": config.get("validate_url") or "",
            "extra_headers": dict(config.get("extra_headers") or {}),
            "user_agent": config.get("user_agent") or "",
        }

        # Upsert
        for i, p in enumerate(platforms):
            if p.get("id") == platform_id:
                platforms[i] = entry
                self._write_all(platforms)
                return entry

        platforms.append(entry)
        self._write_all(platforms)
        return entry

    def delete(self, platform_id: str) -> bool:
        """Delete a custom platform config. Returns True if found and deleted."""
        self._validate_id(platform_id)
        platforms = self._read_all()
        before = len(platforms)
        platforms = [p for p in platforms if p.get("id") != platform_id]
        if len(platforms) < before:
            self._write_all(platforms)
            return True
        return False

    def get_all_domains(self) -> dict[str, str]:
        """Return domain -> platform_id mapping for all custom platforms."""
        mapping: dict[str, str] = {}
        for p in self._read_all():
            pid = p.get("id", "")
            for d in p.get("domains") or []:
                mapping[d] = pid
        return mapping
