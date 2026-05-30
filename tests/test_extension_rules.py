"""Tests to validate Chrome extension rules.js keyword lists against Python rules.py.

Verifies that:
1. extension/rules.js contains at least 50 keywords
2. The JS keywords are a subset of the Python keyword lists
3. Keywords are properly distributed across categories
"""

import re
from pathlib import Path


def _extract_js_keywords(js_content: str, array_name: str) -> list[str]:
    """Extract keyword array from rules.js content.

    Parses JavaScript const array declarations like:
        const SCAM_KEYWORDS = ["word1", "word2", ...];
    """
    # Match the array declaration
    pattern = rf'const\s+{array_name}\s*=\s*\[(.*?)\];'
    match = re.search(pattern, js_content, re.DOTALL)
    assert match, f"Could not find {array_name} array in rules.js"

    array_content = match.group(1)
    # Extract all quoted strings
    keywords = re.findall(r'"([^"]+)"', array_content)
    return keywords


def _get_python_keywords() -> tuple[list[str], list[str], list[str]]:
    """Import the Python keyword lists from src/core/rules.py."""
    from src.core.rules import _ADVERTORIAL_KEYWORDS, _ANXIETY_PHRASES, _SCAM_KEYWORDS

    return list(_SCAM_KEYWORDS), list(_ANXIETY_PHRASES), list(_ADVERTORIAL_KEYWORDS)


def _read_rules_js() -> str:
    """Read the extension/rules.js file."""
    rules_path = Path(__file__).parent.parent / "extension" / "rules.js"
    assert rules_path.exists(), f"extension/rules.js not found at {rules_path}"
    return rules_path.read_text(encoding="utf-8")


class TestExtensionKeywords:
    """Tests for Chrome extension keyword coverage."""

    def test_rules_js_exists(self):
        """Verify extension/rules.js file exists."""
        rules_path = Path(__file__).parent.parent / "extension" / "rules.js"
        assert rules_path.exists()

    def test_manifest_valid_json(self):
        """Verify extension/manifest.json is valid JSON."""
        import json

        manifest_path = Path(__file__).parent.parent / "extension" / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["manifest_version"] == 3
        assert "content_scripts" in data
        assert "background" in data

    def test_at_least_50_keywords(self):
        """Extension must contain at least 50 keywords total."""
        js_content = _read_rules_js()
        scam = _extract_js_keywords(js_content, "SCAM_KEYWORDS")
        anxiety = _extract_js_keywords(js_content, "ANXIETY_PHRASES")
        advertorial = _extract_js_keywords(js_content, "ADVERTORIAL_KEYWORDS")

        total = len(scam) + len(anxiety) + len(advertorial)
        assert total >= 50, f"Expected at least 50 keywords, got {total}"

    def test_scam_keywords_count(self):
        """Extension should have at least 15 scam keywords."""
        js_content = _read_rules_js()
        scam = _extract_js_keywords(js_content, "SCAM_KEYWORDS")
        assert len(scam) >= 15, f"Expected at least 15 scam keywords, got {len(scam)}"

    def test_anxiety_phrases_count(self):
        """Extension should have at least 10 anxiety phrases."""
        js_content = _read_rules_js()
        anxiety = _extract_js_keywords(js_content, "ANXIETY_PHRASES")
        assert len(anxiety) >= 10, f"Expected at least 10 anxiety phrases, got {len(anxiety)}"

    def test_advertorial_keywords_count(self):
        """Extension should have at least 10 advertorial keywords."""
        js_content = _read_rules_js()
        advertorial = _extract_js_keywords(js_content, "ADVERTORIAL_KEYWORDS")
        assert len(advertorial) >= 10, f"Expected at least 10 advertorial keywords, got {len(advertorial)}"

    def test_scam_keywords_subset_of_python(self):
        """JS scam keywords should be a subset of Python scam keywords."""
        js_content = _read_rules_js()
        js_keywords = set(_extract_js_keywords(js_content, "SCAM_KEYWORDS"))
        py_scam, _, _ = _get_python_keywords()
        py_keywords = set(py_scam)

        not_in_python = js_keywords - py_keywords
        assert not not_in_python, (
            f"JS scam keywords not found in Python rules: {not_in_python}"
        )

    def test_anxiety_phrases_subset_of_python(self):
        """JS anxiety phrases should be a subset of Python anxiety phrases."""
        js_content = _read_rules_js()
        js_keywords = set(_extract_js_keywords(js_content, "ANXIETY_PHRASES"))
        _, py_anxiety, _ = _get_python_keywords()
        py_keywords = set(py_anxiety)

        not_in_python = js_keywords - py_keywords
        assert not not_in_python, (
            f"JS anxiety phrases not found in Python rules: {not_in_python}"
        )

    def test_advertorial_keywords_subset_of_python(self):
        """JS advertorial keywords should be a subset of Python advertorial keywords."""
        js_content = _read_rules_js()
        js_keywords = set(_extract_js_keywords(js_content, "ADVERTORIAL_KEYWORDS"))
        _, _, py_advertorial = _get_python_keywords()
        py_keywords = set(py_advertorial)

        not_in_python = js_keywords - py_keywords
        assert not not_in_python, (
            f"JS advertorial keywords not found in Python rules: {not_in_python}"
        )

    def test_score_content_function_exists(self):
        """Verify scoreContent function is defined in rules.js."""
        js_content = _read_rules_js()
        assert "function scoreContent" in js_content

    def test_extension_files_complete(self):
        """Verify all required extension files exist."""
        ext_dir = Path(__file__).parent.parent / "extension"
        required_files = [
            "manifest.json",
            "rules.js",
            "content.js",
            "background.js",
            "popup.html",
            "popup.js",
            "popup.css",
            "icons/icon-green.svg",
            "icons/icon-yellow.svg",
            "icons/icon-red.svg",
            "icons/icon-gray.svg",
        ]
        for filename in required_files:
            filepath = ext_dir / filename
            assert filepath.exists(), f"Missing required file: {filename}"
