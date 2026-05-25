"""Prompt loader — selects prompt template based on language preference."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Prompt templates directory
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Supported languages and their prompt files
_PROMPT_FILES = {
    "zh": "score_content.txt",
    "en": "score_content_en.txt",
    "fast": "score_content_fast.txt",
}

# System prompt files (for prompt injection defense)
_SYSTEM_PROMPT_FILES = {
    "zh": "score_content_system.txt",
    "en": "score_content_en_system.txt",
    "fast": "score_content_fast_system.txt",
}

# Cache loaded templates
_template_cache: dict[str, str] = {}
_system_template_cache: dict[str, str] = {}


def get_prompt_template(language: str = "zh") -> str:
    """Load the scoring prompt template for the specified language.

    Args:
        language: Language code ("zh" or "en"). Defaults to "zh".
                 Falls back to "zh" if the requested language is not available.

    Returns:
        The prompt template string with {content} placeholder.
    """
    # Normalize and validate
    lang = language.lower().strip()
    if lang not in _PROMPT_FILES:
        logger.warning(f"Unsupported language '{lang}', falling back to 'zh'")
        lang = "zh"

    # Check cache
    if lang in _template_cache:
        return _template_cache[lang]

    # Load from disk
    prompt_file = _PROMPTS_DIR / _PROMPT_FILES[lang]
    if not prompt_file.exists():
        logger.warning(f"Prompt file not found: {prompt_file}, falling back to 'zh'")
        lang = "zh"
        prompt_file = _PROMPTS_DIR / _PROMPT_FILES[lang]

    template = prompt_file.read_text(encoding="utf-8")
    _template_cache[lang] = template
    logger.debug(f"Loaded prompt template for language '{lang}'")
    return template


def get_system_prompt(language: str = "zh") -> str:
    """Load the system prompt for the specified language.

    System prompts contain only the scoring rubric and instructions,
    without any content placeholder. Used for prompt injection defense
    by separating instructions (system message) from content (user message).

    Args:
        language: Language code ("zh", "en", or "fast"). Defaults to "zh".
                 Falls back to "zh" if the requested language is not available.

    Returns:
        The system prompt string (no {content} placeholder).
    """
    # Normalize and validate
    lang = language.lower().strip()
    if lang not in _SYSTEM_PROMPT_FILES:
        logger.warning(f"Unsupported language '{lang}' for system prompt, falling back to 'zh'")
        lang = "zh"

    # Check cache
    if lang in _system_template_cache:
        return _system_template_cache[lang]

    # Load from disk
    prompt_file = _PROMPTS_DIR / _SYSTEM_PROMPT_FILES[lang]
    if not prompt_file.exists():
        logger.warning(f"System prompt file not found: {prompt_file}, falling back to 'zh'")
        lang = "zh"
        prompt_file = _PROMPTS_DIR / _SYSTEM_PROMPT_FILES[lang]

    template = prompt_file.read_text(encoding="utf-8")
    _system_template_cache[lang] = template
    logger.debug(f"Loaded system prompt for language '{lang}'")
    return template


def get_available_languages() -> list[str]:
    """Return list of supported language codes."""
    return list(_PROMPT_FILES.keys())


def clear_cache() -> None:
    """Clear the template cache (useful for testing or config reload)."""
    _template_cache.clear()
    _system_template_cache.clear()
