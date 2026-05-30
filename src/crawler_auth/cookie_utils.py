"""Utilities for parsing and importing cookies from external sources."""
from __future__ import annotations

import json
import re
import subprocess
import sys


def parse_cookie_string(raw: str) -> dict[str, str]:
    """Parse cookies from a browser Cookie header or semicolon-separated string."""
    text = raw.strip()
    if not text:
        raise ValueError("Empty cookie string")

    # JSON object: {"z_c0": "...", "__zse_ck": "..."}
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON cookie format: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON cookies must be an object")
        return {str(k): str(v) for k, v in data.items() if v is not None}

    # Strip optional "Cookie:" prefix from copied request headers
    text = re.sub(r"^cookie:\s*", "", text, flags=re.IGNORECASE)

    cookies: dict[str, str] = {}
    for item in re.split(r"[;\n]", text):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            cookies[name] = value

    if not cookies:
        raise ValueError("No valid cookies found in input")
    return cookies


def read_clipboard() -> str:
    """Read text from the system clipboard."""
    if sys.platform == "darwin":
        cmd = ["pbpaste"]
    elif sys.platform == "win32":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Clipboard -Raw",
        ]
    else:
        for cmd in (["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]):
            try:
                return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        raise RuntimeError(
            "Clipboard not supported on this platform. "
            "Use --cookie or --file instead."
        )

    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except FileNotFoundError as exc:
        raise RuntimeError("Clipboard tool not available") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Failed to read clipboard") from exc
