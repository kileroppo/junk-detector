"""Tests for src/extractors/web.py — web content extraction helpers."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.extractors.web import _extract_title, _find_main_content, _strip_noise


class TestStripNoise:
    """Tests for _strip_noise."""

    def test_removes_script_tags(self):
        """_strip_noise removes script tags."""
        html = "<div><p>Content</p><script>alert('hi')</script></div>"
        soup = BeautifulSoup(html, "html.parser")
        _strip_noise(soup)

        assert soup.find("script") is None
        assert "Content" in soup.get_text()

    def test_removes_style_tags(self):
        """_strip_noise removes style tags."""
        html = "<div><p>Content</p><style>.x{color:red}</style></div>"
        soup = BeautifulSoup(html, "html.parser")
        _strip_noise(soup)

        assert soup.find("style") is None

    def test_removes_nav_tags(self):
        """_strip_noise removes nav elements."""
        html = "<div><nav>Menu</nav><p>Content</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        _strip_noise(soup)

        assert soup.find("nav") is None
        assert "Content" in soup.get_text()

    def test_removes_elements_with_noisy_class(self):
        """_strip_noise removes elements with ad/nav class names."""
        html = '<div><div class="advertisement">Ad here</div><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        _strip_noise(soup)

        assert "Ad here" not in soup.get_text()
        assert "Content" in soup.get_text()

    def test_removes_elements_with_noisy_id(self):
        """_strip_noise removes elements with sidebar/footer id."""
        html = '<div><div id="sidebar">Side</div><p>Content</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        _strip_noise(soup)

        assert "Side" not in soup.get_text()


class TestFindMainContent:
    """Tests for _find_main_content."""

    def test_finds_article_tag(self):
        """_find_main_content finds <article> tag."""
        html = "<body><article><p>Article content here</p></article></body>"
        soup = BeautifulSoup(html, "html.parser")
        result = _find_main_content(soup)

        assert result is not None
        assert "Article content" in result.get_text()

    def test_finds_main_tag(self):
        """_find_main_content finds <main> tag when no <article>."""
        html = "<body><main><p>Main content here</p></main></body>"
        soup = BeautifulSoup(html, "html.parser")
        result = _find_main_content(soup)

        assert result is not None
        assert "Main content" in result.get_text()

    def test_finds_role_main(self):
        """_find_main_content finds element with role=main."""
        html = '<body><div role="main"><p>Role main content</p></div></body>'
        soup = BeautifulSoup(html, "html.parser")
        result = _find_main_content(soup)

        assert result is not None
        assert "Role main content" in result.get_text()

    def test_returns_none_for_empty_page(self):
        """_find_main_content returns None for page with no discernible content."""
        html = "<body></body>"
        soup = BeautifulSoup(html, "html.parser")
        result = _find_main_content(soup)

        assert result is None


class TestExtractTitle:
    """Tests for _extract_title."""

    def test_extracts_from_title_tag(self):
        """_extract_title gets text from <title>."""
        html = "<html><head><title>My Page Title</title></head><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title(soup)

        assert title == "My Page Title"

    def test_extracts_from_h1_when_no_title(self):
        """_extract_title falls back to <h1> when no <title>."""
        html = "<body><h1>Heading One</h1><p>content</p></body>"
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title(soup)

        assert title == "Heading One"

    def test_returns_none_when_no_title_or_h1(self):
        """_extract_title returns None when neither title nor h1 present."""
        html = "<body><p>Just some text</p></body>"
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title(soup)

        assert title is None
