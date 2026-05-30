"""Persistent user settings (model API keys, etc.) stored locally."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.core.model_presets import get_provider

_SETTINGS_DIR = Path.home() / ".junk_detector"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"


def _ensure_dir() -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)


def load_user_settings() -> dict[str, Any]:
    """Load user settings from disk."""
    if not _SETTINGS_FILE.exists():
        return {}
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_user_settings(data: dict[str, Any]) -> None:
    """Persist user settings with restrictive permissions."""
    _ensure_dir()
    _SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.chmod(_SETTINGS_FILE, 0o600)


def get_llm_settings() -> dict[str, Any]:
    return load_user_settings().get("llm", {})


def mask_api_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:4]}••••{key[-4:]}"


def get_llm_settings_display() -> dict[str, Any]:
    """Return LLM settings for UI (API key masked)."""
    llm = get_llm_settings()
    if not llm:
        preset = get_provider("deepseek")
        return {
            "provider": "deepseek",
            "model": preset["default_model"],
            "api_base": preset.get("default_base", ""),
            "api_key_masked": "",
            "configured": False,
        }
    return {
        **llm,
        "api_key_masked": mask_api_key(llm.get("api_key", "")),
        "configured": bool(llm.get("api_key") or llm.get("provider") == "ollama"),
    }


def save_llm_settings(
    *,
    provider: str,
    model: str,
    api_base: str = "",
    api_key: str | None = None,
) -> dict[str, Any]:
    """Save LLM settings; empty api_key keeps the existing key."""
    settings = load_user_settings()
    existing = settings.get("llm", {})

    llm = {
        "provider": provider,
        "model": model.strip(),
        "api_base": api_base.strip(),
        "api_key": (api_key or "").strip() or existing.get("api_key", ""),
    }
    settings["llm"] = llm
    save_user_settings(settings)
    apply_llm_settings(llm)
    return llm


def apply_llm_settings(llm: dict[str, Any] | None = None) -> None:
    """Apply LLM settings to process environment for LiteLLM."""
    llm = llm if llm is not None else get_llm_settings()
    if not llm:
        return

    provider = llm.get("provider", "deepseek")
    preset = get_provider(provider)
    api_key = llm.get("api_key", "")
    api_base = llm.get("api_base") or preset.get("default_base", "")

    key_env = preset.get("api_key_env")
    if key_env and api_key:
        os.environ[key_env] = api_key

    if provider == "ollama":
        if api_base:
            os.environ["OLLAMA_API_BASE"] = api_base
    elif provider == "custom":
        if api_base:
            os.environ["OPENAI_API_BASE"] = api_base
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
    elif api_base:
        # Provider-specific base URL env vars used by LiteLLM
        base_env_map = {
            "deepseek": "DEEPSEEK_API_BASE",
            "openai": "OPENAI_API_BASE",
            "anthropic": "ANTHROPIC_API_BASE",
            "zhipu": "ZHIPUAI_API_BASE",
            "moonshot": "MOONSHOT_API_BASE",
        }
        env_name = base_env_map.get(provider)
        if env_name:
            os.environ[env_name] = api_base


def apply_saved_llm_settings() -> None:
    """Load and apply saved LLM settings on startup."""
    apply_llm_settings(get_llm_settings())


READING_PROFILE_GENERAL = "general"
READING_PROFILE_TECH_ROUNDUP = "tech_roundup"

READING_PROFILE_LABELS: dict[str, str] = {
    READING_PROFILE_GENERAL: "通用阅读",
    READING_PROFILE_TECH_ROUNDUP: "常读技术目录 / 工具清单",
}


def get_reading_profile() -> str:
    profile = load_user_settings().get("reading_profile", READING_PROFILE_GENERAL)
    if profile not in READING_PROFILE_LABELS:
        return READING_PROFILE_GENERAL
    return profile


def save_reading_profile(profile: str) -> str:
    if profile not in READING_PROFILE_LABELS:
        profile = READING_PROFILE_GENERAL
    settings = load_user_settings()
    settings["reading_profile"] = profile
    save_user_settings(settings)
    return profile


def get_scoring_mode() -> str:
    from src.core.scoring_modes import MODE_CONSUMER, MODE_LABELS

    mode = load_user_settings().get("scoring_mode", MODE_CONSUMER)
    return mode if mode in MODE_LABELS else MODE_CONSUMER


def save_scoring_mode(mode: str) -> str:
    from src.core.scoring_modes import MODE_CONSUMER, MODE_LABELS

    if mode not in MODE_LABELS:
        mode = MODE_CONSUMER
    settings = load_user_settings()
    settings["scoring_mode"] = mode
    save_user_settings(settings)
    return mode


def has_llm_api_key() -> bool:
    """Check if any LLM API key is available."""
    llm = get_llm_settings()
    if llm.get("api_key"):
        return True
    if llm.get("provider") == "ollama":
        return True
    env_keys = (
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ZHIPUAI_API_KEY",
        "MOONSHOT_API_KEY",
    )
    return any(os.environ.get(k) for k in env_keys)
