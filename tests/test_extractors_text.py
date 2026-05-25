"""Tests for src/extractors/text.py — text and file content extraction."""

from __future__ import annotations

import pytest

from src.extractors.text import extract_from_file, extract_from_text
from src.models.score import InputType


class TestExtractFromText:
    """Tests for extract_from_text."""

    def test_valid_text_returns_content(self):
        """extract_from_text with valid text returns Content with correct fields."""
        content = extract_from_text("Hello, world!")

        assert content.input_type == InputType.TEXT
        assert content.text == "Hello, world!"
        assert content.content_hash != ""
        assert content.title is None

    def test_with_title_sets_title(self):
        """extract_from_text with title sets the title."""
        content = extract_from_text("Some text", title="My Title")

        assert content.title == "My Title"
        assert content.text == "Some text"

    def test_strips_whitespace(self):
        """extract_from_text strips leading/trailing whitespace."""
        content = extract_from_text("  \n  Hello  \n  ")

        assert content.text == "Hello"

    def test_empty_text_raises_value_error(self):
        """extract_from_text with empty text raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            extract_from_text("")

    def test_whitespace_only_raises_value_error(self):
        """extract_from_text with whitespace-only text raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            extract_from_text("   \n\t  ")

    def test_hash_is_computed(self):
        """extract_from_text computes a SHA256 hash."""
        content = extract_from_text("Test content")

        assert len(content.content_hash) == 64  # SHA256 hex digest length


class TestExtractFromFile:
    """Tests for extract_from_file."""

    def test_valid_file(self, tmp_path):
        """extract_from_file with valid file returns Content."""
        file = tmp_path / "test_article.txt"
        file.write_text("This is file content.", encoding="utf-8")

        content = extract_from_file(str(file))

        assert content.input_type == InputType.FILE
        assert content.text == "This is file content."
        assert content.content_hash != ""

    def test_uses_filename_stem_as_title(self, tmp_path):
        """extract_from_file uses filename stem as title."""
        file = tmp_path / "my_document.md"
        file.write_text("Document text", encoding="utf-8")

        content = extract_from_file(str(file))

        assert content.title == "my_document"

    def test_nonexistent_path_raises_file_not_found(self):
        """extract_from_file with nonexistent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            extract_from_file("/nonexistent/path/file.txt")

    def test_empty_file_raises_value_error(self, tmp_path):
        """extract_from_file with empty file raises ValueError."""
        file = tmp_path / "empty.txt"
        file.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="empty"):
            extract_from_file(str(file))

    def test_directory_path_raises_value_error(self, tmp_path):
        """extract_from_file with directory path raises ValueError."""
        with pytest.raises(ValueError, match="not a file"):
            extract_from_file(str(tmp_path))

    def test_sets_source_url(self, tmp_path):
        """extract_from_file sets source_url to the resolved file path."""
        file = tmp_path / "source.txt"
        file.write_text("Content here", encoding="utf-8")

        content = extract_from_file(str(file))

        assert content.source_url is not None
        assert "source.txt" in content.source_url
