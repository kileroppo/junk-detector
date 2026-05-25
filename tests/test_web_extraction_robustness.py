"""Robustness tests for web extraction with real-world Chinese HTML layouts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.extractors.web import (
    _extract_text,
    _extract_title,
    _find_main_content,
    _strip_noise,
    extract_from_url,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _process_html(html: str) -> str:
    """Run the full extraction pipeline on raw HTML and return extracted text."""
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    main_content = _find_main_content(soup)
    if main_content:
        return _extract_text(main_content)
    return ""


class TestChineseBlogExtraction:
    """Tests with CSDN/juejin-like blog layout."""

    @pytest.fixture()
    def blog_html(self) -> str:
        return _load_fixture("chinese_blog_with_sidebar.html")

    def test_chinese_blog_strips_sidebar(self, blog_html: str):
        """Sidebar hot articles list is removed from extracted text."""
        text = _process_html(blog_html)

        assert "热门文章" not in text
        assert "如何学好机器学习" not in text
        assert "Docker入门指南" not in text
        # Article text is preserved
        assert "Python异步编程" in text
        assert "asyncio模块" in text

    def test_chinese_blog_strips_navigation(self, blog_html: str):
        """Navigation bar links are removed from extracted text."""
        text = _process_html(blog_html)

        assert "首页" not in text
        assert "前端" not in text

    def test_chinese_blog_strips_ads(self, blog_html: str):
        """Advertisement content is removed from extracted text."""
        text = _process_html(blog_html)

        assert "广告" not in text
        assert "限时优惠" not in text
        assert "促销广告横幅" not in text

    def test_chinese_blog_strips_comments(self, blog_html: str):
        """Comment section is removed from extracted text."""
        text = _process_html(blog_html)

        assert "用户评论" not in text
        assert "写得太好了" not in text
        assert "请问有源代码吗" not in text

    def test_chinese_blog_preserves_article_body(self, blog_html: str):
        """Full article body text is preserved after noise removal."""
        text = _process_html(blog_html)

        assert "Python异步编程是现代Python开发中不可或缺的技能" in text
        assert "async和await关键字" in text
        assert "事件循环" in text
        assert "Web爬虫" in text


class TestWeChatExtraction:
    """Tests with WeChat public account article layout."""

    @pytest.fixture()
    def wechat_html(self) -> str:
        return _load_fixture("wechat_article.html")

    def test_wechat_strips_share_buttons(self, wechat_html: str):
        """Share and social buttons are removed."""
        text = _process_html(wechat_html)

        assert "分享到朋友圈" not in text
        assert "发送给好友" not in text
        assert "点赞 128" not in text

    def test_wechat_strips_recommendations(self, wechat_html: str):
        """Recommended reading section is removed."""
        text = _process_html(wechat_html)

        assert "推荐阅读" not in text
        assert "GPT-4技术解析" not in text
        assert "LangChain实战教程" not in text

    def test_wechat_strips_qr_code(self, wechat_html: str):
        """QR code section is removed."""
        text = _process_html(wechat_html)

        assert "长按识别二维码" not in text
        assert "关注公众号" not in text

    def test_wechat_preserves_article_body(self, wechat_html: str):
        """WeChat article body text is preserved."""
        text = _process_html(wechat_html)

        assert "大语言模型技术的快速发展" in text
        assert "提示工程的基本原理" in text
        assert "RAG检索增强生成架构" in text


class TestExtractFromUrlWithFixtures:
    """Integration tests using extract_from_url with mocked httpx."""

    @pytest.fixture()
    def blog_html(self) -> str:
        return _load_fixture("chinese_blog_with_sidebar.html")

    @pytest.fixture()
    def wechat_html(self) -> str:
        return _load_fixture("wechat_article.html")

    async def test_extract_from_url_chinese_blog(self, blog_html: str):
        """extract_from_url returns clean Content from a Chinese blog page."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = blog_html
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.extractors.web.httpx.AsyncClient", return_value=mock_client):
            content = await extract_from_url("http://blog.example.com/article")

        assert content.text is not None
        assert "Python异步编程" in content.text
        assert "asyncio模块" in content.text
        # Noise should be gone
        assert "热门文章" not in content.text
        assert "广告" not in content.text
        # Title should be extracted
        assert content.title is not None
        assert "Python异步编程" in content.title

    async def test_extract_from_url_wechat(self, wechat_html: str):
        """extract_from_url returns clean Content from a WeChat article."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = wechat_html
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.extractors.web.httpx.AsyncClient", return_value=mock_client):
            content = await extract_from_url("http://mp.weixin.qq.com/s/example")

        assert content.text is not None
        assert "大语言模型技术" in content.text
        assert "提示工程" in content.text
        # Noise should be gone
        assert "分享到朋友圈" not in content.text
        assert "推荐阅读" not in content.text

    async def test_extract_from_url_minimal_content(self):
        """extract_from_url handles pages with minimal main content."""
        html = """<!DOCTYPE html>
        <html><head><title>Empty Page</title></head>
        <body>
        <nav>Navigation links</nav>
        <div class="sidebar">Sidebar stuff</div>
        <div><p>Short text here.</p></div>
        <footer>Footer info</footer>
        </body></html>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("src.extractors.web.httpx.AsyncClient", return_value=mock_client):
            content = await extract_from_url("http://example.com/sparse")

        # Should still extract something
        assert content.text is not None
        assert len(content.text.strip()) > 0


class TestTitleExtractionChinese:
    """Tests for title extraction with Chinese content."""

    def test_title_extraction_with_site_suffix(self):
        """Title extraction works with Chinese title containing site name."""
        html = "<html><head><title>Python教程 - CSDN博客</title></head><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title(soup)

        assert title == "Python教程 - CSDN博客"

    def test_title_extraction_chinese_h1_fallback(self):
        """Title extraction falls back to h1 with Chinese text."""
        html = "<body><h1>深度学习入门教程</h1><p>内容</p></body>"
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_title(soup)

        assert title == "深度学习入门教程"
