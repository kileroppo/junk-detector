"""Tests for src/extractors/sources/ - Chinese content source fetchers."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from src.extractors.sources import MonitorItem, SourceFetcher
from src.extractors.sources.weibo_hot import WeiboHotFetcher
from src.extractors.sources.zhihu_hot import ZhihuHotFetcher
from src.extractors.sources.wechat_sogou import WechatSogouFetcher


class TestMonitorItem:
    """Tests for MonitorItem dataclass."""

    def test_create_item(self):
        """MonitorItem can be created with required fields."""
        item = MonitorItem(title="Test", url="https://example.com", source="test")
        assert item.title == "Test"
        assert item.url == "https://example.com"
        assert item.source == "test"
        assert item.timestamp  # auto-generated
        assert item.snippet == ""

    def test_item_with_snippet(self):
        """MonitorItem can have optional snippet."""
        item = MonitorItem(title="T", url="http://x.com", source="s", snippet="hello")
        assert item.snippet == "hello"


class TestSourceFetcherProtocol:
    """Tests for the SourceFetcher protocol."""

    def test_weibo_implements_protocol(self):
        """WeiboHotFetcher implements SourceFetcher protocol."""
        fetcher = WeiboHotFetcher()
        assert hasattr(fetcher, "source_name")
        assert hasattr(fetcher, "fetch_items")

    def test_zhihu_implements_protocol(self):
        """ZhihuHotFetcher implements SourceFetcher protocol."""
        fetcher = ZhihuHotFetcher()
        assert hasattr(fetcher, "source_name")
        assert hasattr(fetcher, "fetch_items")

    def test_wechat_implements_protocol(self):
        """WechatSogouFetcher implements SourceFetcher protocol."""
        fetcher = WechatSogouFetcher()
        assert hasattr(fetcher, "source_name")
        assert hasattr(fetcher, "fetch_items")


class TestWeiboHotFetcher:
    """Tests for WeiboHotFetcher."""

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Successful fetch returns list of MonitorItems."""
        mock_data = {
            "data": {
                "realtime": [
                    {"word": "热搜话题1", "label_name": "新"},
                    {"word": "热搜话题2", "label_name": "热"},
                    {"word": "", "label_name": ""},  # empty should be skipped
                ]
            }
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = WeiboHotFetcher()
            fetcher._last_fetch = 0  # bypass rate limit
            items = await fetcher.fetch_items()

        assert len(items) == 2
        assert items[0].title == "热搜话题1"
        assert items[0].source == "weibo"
        assert "weibo.com" in items[0].url

    @pytest.mark.asyncio
    async def test_fetch_network_error_returns_empty(self):
        """Network error returns empty list without raising."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = WeiboHotFetcher()
            fetcher._last_fetch = 0
            items = await fetcher.fetch_items()

        assert items == []


class TestZhihuHotFetcher:
    """Tests for ZhihuHotFetcher."""

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Successful fetch returns list of MonitorItems."""
        mock_data = {
            "data": [
                {"target": {"title": "知乎热门问题", "id": "12345", "excerpt": "摘要文本"}},
                {"target": {"title": "另一个问题", "id": "67890", "excerpt": ""}},
                {"target": {"title": "", "id": "99999", "excerpt": ""}},  # empty title skipped
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = ZhihuHotFetcher()
            fetcher._last_fetch = 0
            items = await fetcher.fetch_items()

        assert len(items) == 2
        assert items[0].title == "知乎热门问题"
        assert items[0].source == "zhihu"
        assert "zhihu.com" in items[0].url

    @pytest.mark.asyncio
    async def test_fetch_network_error_returns_empty(self):
        """Network error returns empty list without raising."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("Timeout"))

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = ZhihuHotFetcher()
            fetcher._last_fetch = 0
            items = await fetcher.fetch_items()

        assert items == []


class TestWechatSogouFetcher:
    """Tests for WechatSogouFetcher."""

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        """Successful fetch parses HTML and returns items."""
        html_content = '''
        <html><body>
        <ul class="news-list">
            <li><div class="txt-box"><a href="/link/1">微信文章标题</a><p class="txt-info">文章摘要</p></div></li>
            <li><div class="txt-box"><a href="/link/2">另一篇文章</a><p class="txt-info">另一个摘要</p></div></li>
        </ul>
        </body></html>
        '''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = WechatSogouFetcher(query="test")
            fetcher._last_fetch = 0
            items = await fetcher.fetch_items()

        assert len(items) == 2
        assert items[0].title == "微信文章标题"
        assert items[0].source == "wechat"

    @pytest.mark.asyncio
    async def test_fetch_network_error_returns_empty(self):
        """Network error returns empty list without raising."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("Blocked"))

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = WechatSogouFetcher()
            fetcher._last_fetch = 0
            items = await fetcher.fetch_items()

        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_empty_html_returns_empty(self):
        """Empty HTML returns empty list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("src.extractors.http_pool.get_client", return_value=mock_client):
            fetcher = WechatSogouFetcher()
            fetcher._last_fetch = 0
            items = await fetcher.fetch_items()

        assert items == []
