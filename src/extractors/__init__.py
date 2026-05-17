"""Content extractors for web, text, and file inputs."""

from src.extractors.text import extract_from_file, extract_from_text
from src.extractors.web import extract_from_url

# Playwright-based extractor (optional dependency)
try:
    from src.extractors.playwright_web import (
        extract_from_url_playwright,
        is_spa_url,
        smart_extract,
    )

    _has_playwright_extractor = True
except ImportError:
    _has_playwright_extractor = False

__all__ = [
    "extract_from_url",
    "extract_from_text",
    "extract_from_file",
    "extract_from_url_playwright",
    "is_spa_url",
    "smart_extract",
]
