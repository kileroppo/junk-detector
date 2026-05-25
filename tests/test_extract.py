"""Tests for content extraction (src.extractors.web and src.extractors.text).

Verifies URL extraction with mocked httpx and text extraction behavior.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.extractors.text import extract_from_text
from src.models.score import Content, InputType


class TestExtractFromUrl:
    """Tests for extract_from_url() with mocked HTTP client."""

    @patch("src.extractors.web.httpx.AsyncClient")
    async def test_extracts_title_and_body(self, mock_client_cls):
        """Successful extraction parses title and body text from HTML."""
        from src.extractors.web import extract_from_url

        html = """
        <html>
        <head><title>Test Article Title</title></head>
        <body>
            <article>
                <p>This is the main article content with enough text to pass extraction checks and validation.</p>
                <p>A second paragraph to add more body text for the extractor to find and extract properly.</p>
            </article>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        content = await extract_from_url("https://example.com/article")
        assert content.title == "Test Article Title"
        assert content.input_type == InputType.URL
        assert len(content.text) > 0

    @patch("src.extractors.web.httpx.AsyncClient")
    async def test_handles_missing_title(self, mock_client_cls):
        """When HTML has no title or h1, title should be None."""
        from src.extractors.web import extract_from_url

        html = """
        <html>
        <body>
            <article>
                <p>Article content without any title tag. This must be long enough to pass validation.</p>
                <p>Additional paragraph to make the content substantial for extraction to succeed.</p>
            </article>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        content = await extract_from_url("https://example.com/no-title")
        assert content.title is None

    @patch("src.extractors.web.httpx.AsyncClient")
    async def test_handles_connection_error(self, mock_client_cls):
        """Network errors raise ValueError with descriptive message."""
        import httpx

        from src.extractors.web import extract_from_url

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.RequestError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(ValueError, match="Failed to fetch URL"):
            await extract_from_url("https://unreachable.example.com")

    @patch("src.extractors.web.httpx.AsyncClient")
    async def test_handles_timeout(self, mock_client_cls):
        """Timeout raises TimeoutError."""
        import httpx

        from src.extractors.web import extract_from_url

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(TimeoutError):
            await extract_from_url("https://slow.example.com")


class TestExtractFromText:
    """Tests for extract_from_text()."""

    def test_creates_content_with_hash(self):
        """extract_from_text returns Content with a computed content_hash."""
        content = extract_from_text("Hello, this is test content")
        assert isinstance(content, Content)
        assert content.input_type == InputType.TEXT
        assert content.content_hash != ""
        assert len(content.content_hash) == 64  # SHA256 hex

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped from input text."""
        content = extract_from_text("  trimmed content  ")
        assert content.text == "trimmed content"

    def test_empty_text_raises_value_error(self):
        """Empty or whitespace-only text raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            extract_from_text("   ")
