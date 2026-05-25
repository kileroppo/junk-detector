"""Configuration loader for junk-detector.

Loads config.yaml from project root, with .env overrides for API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.models.score import ScoringConfig

_cached_yaml: dict | None = None


def _find_config_file() -> Path | None:
    """Find config.yaml in cwd or project root (where pyproject.toml lives)."""
    # Try cwd first
    cwd_config = Path.cwd() / "config.yaml"
    if cwd_config.exists():
        return cwd_config

    # Try project root (relative to this file)
    project_root = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    if project_root.exists():
        return project_root

    return None


def _load_yaml() -> dict[str, Any]:
    """Load and parse config.yaml, returning empty dict if not found.

    Uses a module-level cache to avoid repeated disk reads.
    Call reload_config() to clear the cache.
    """
    global _cached_yaml
    if _cached_yaml is not None:
        return _cached_yaml

    config_path = _find_config_file()
    if config_path is None:
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    result = data if isinstance(data, dict) else {}
    _cached_yaml = result
    return result


def reload_config() -> None:
    """Clear the cached config, forcing a re-read from disk on next access."""
    global _cached_yaml
    _cached_yaml = None


def get_model_config(override_model: str | None = None) -> dict[str, Any]:
    """Return the active model preset configuration.

    Args:
        override_model: If provided, use this preset name instead of config/env.

    Returns:
        Dict with keys: primary, fallback, and optionally api_base.
        Returns default deepseek config if no config file found.
    """
    data = _load_yaml()

    # Determine active model: CLI override > env var > config file > default
    active = override_model
    if active is None:
        active = os.environ.get("JUNK_DETECTOR_MODEL")
    if active is None:
        active = data.get("active_model", "deepseek")

    models = data.get("models", {})
    preset = models.get(active)

    if preset is None:
        # Fallback to defaults if preset not found
        return {
            "primary": "deepseek/deepseek-chat",
            "fallback": "deepseek/deepseek-chat",
        }

    # If using Ollama, set OLLAMA_API_BASE env var if not already set
    if active == "ollama":
        api_base = preset.get("api_base", "http://localhost:11434")
        if not os.environ.get("OLLAMA_API_BASE"):
            os.environ["OLLAMA_API_BASE"] = api_base

    return {
        "primary": preset.get("primary", "deepseek/deepseek-chat"),
        "fallback": preset.get("fallback", preset.get("primary", "deepseek/deepseek-chat")),
        "api_base": preset.get("api_base"),
    }


def load_config(override_model: str | None = None) -> ScoringConfig:
    """Load full ScoringConfig from config.yaml with env overrides.

    Args:
        override_model: If provided, use this model preset name.

    Returns:
        ScoringConfig populated from config.yaml, falling back to defaults
        for any missing values.
    """
    data = _load_yaml()
    model_cfg = get_model_config(override_model)

    # Build ScoringConfig kwargs
    kwargs: dict[str, Any] = {
        "primary_model": model_cfg["primary"],
        "fallback_model": model_cfg["fallback"],
    }

    # Scoring section
    scoring = data.get("scoring", {})
    if "confidence_threshold" in scoring:
        kwargs["confidence_threshold"] = scoring["confidence_threshold"]
    if "weights" in scoring:
        kwargs["weights"] = scoring["weights"]
    if "label_thresholds" in scoring:
        kwargs["label_thresholds"] = scoring["label_thresholds"]

    # Embedding section
    embedding = data.get("embedding", {})
    if "model" in embedding:
        kwargs["embedding_model"] = embedding["model"]
    if "api_base" in embedding:
        kwargs["embedding_api_base"] = embedding["api_base"]

    # Summarization section
    summarization = data.get("summarization", {})
    if "enabled" in summarization:
        kwargs["summarize_enabled"] = summarization["enabled"]
    if "max_chars_before_summarize" in summarization:
        kwargs["summarize_max_chars"] = summarization["max_chars_before_summarize"]
    if "model" in summarization:
        kwargs["summarize_model"] = summarization["model"]

    # Store api_base for Ollama usage
    if model_cfg.get("api_base"):
        kwargs["api_base"] = model_cfg["api_base"]

    return ScoringConfig(**kwargs)
