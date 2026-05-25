"""Tests for content hydrators (src.core.hydrators).

Covers hydrate_source_reputation and hydrate_article_stats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from src.core.hydrators import hydrate_article_stats, hydrate_source_reputation


@dataclass
class FakeContent:
    """Minimal Content stand-in for testing hydrators."""

    text: str = ""
    source_url: str | None = None


@dataclass
class FakePipelineContext:
    """Minimal PipelineContext stand-in for testing hydrators."""

    raw_input: str = ""
    content: FakeContent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TestHydrateSourceReputation:
    """Tests for hydrate_source_reputation."""

    @pytest.mark.asyncio
    @patch("src.storage.db.query_by_domain")
    async def test_extracts_domain_and_computes_reputation(self, mock_query):
        mock_query.return_value = [60.0, 80.0, 70.0]
        ctx = FakePipelineContext(
            content=FakeContent(
                text="article body",
                source_url="https://news.example.com/article/123",
            )
        )
        result = await hydrate_source_reputation(ctx)
        assert result["source_domain"] == "news.example.com"
        assert result["source_reputation"] == 70.0
        assert result["source_article_count"] == 3
        mock_query.assert_called_once_with("news.example.com", "junk_detector.db")

    @pytest.mark.asyncio
    async def test_no_source_url_returns_none_values(self):
        ctx = FakePipelineContext(
            content=FakeContent(text="no url here", source_url=None)
        )
        result = await hydrate_source_reputation(ctx)
        assert result["source_domain"] is None
        assert result["source_reputation"] is None
        assert result["source_article_count"] == 0

    @pytest.mark.asyncio
    async def test_content_none_returns_none_values(self):
        ctx = FakePipelineContext(content=None, raw_input="raw text")
        result = await hydrate_source_reputation(ctx)
        assert result["source_domain"] is None
        assert result["source_reputation"] is None
        assert result["source_article_count"] == 0

    @pytest.mark.asyncio
    @patch("src.storage.db.query_by_domain")
    async def test_strips_www_prefix(self, mock_query):
        mock_query.return_value = [50.0, 50.0]
        ctx = FakePipelineContext(
            content=FakeContent(
                text="text",
                source_url="https://www.reuters.com/article/1",
            )
        )
        result = await hydrate_source_reputation(ctx)
        assert result["source_domain"] == "reuters.com"
        mock_query.assert_called_once_with("reuters.com", "junk_detector.db")

    @pytest.mark.asyncio
    @patch("src.storage.db.query_by_domain")
    async def test_no_scores_returns_none_reputation(self, mock_query):
        mock_query.return_value = []
        ctx = FakePipelineContext(
            content=FakeContent(
                text="text",
                source_url="https://new-site.com/page",
            )
        )
        result = await hydrate_source_reputation(ctx)
        assert result["source_domain"] == "new-site.com"
        assert result["source_reputation"] is None
        assert result["source_article_count"] == 0


class TestHydrateArticleStats:
    """Tests for hydrate_article_stats."""

    @pytest.mark.asyncio
    async def test_full_text_with_links_and_images(self):
        text = (
            "This is the first paragraph with a link https://example.com/page.\n"
            "\n"
            "Second paragraph has another link http://test.org/data and text.\n"
            "\n"
            "Third paragraph with image ![alt text](https://img.com/pic.png).\n"
            "\n"
            "Fourth paragraph with HTML image <img src='photo.jpg' />.\n"
        )
        ctx = FakePipelineContext(content=FakeContent(text=text))
        result = await hydrate_article_stats(ctx)

        assert result["char_count"] == len(text)
        assert result["paragraph_count"] == 4
        assert result["link_count"] == 3  # example.com, test.org, img.com in markdown
        assert result["image_references"] == 2  # 1 markdown + 1 html
        assert result["has_links"] is True
        assert result["avg_sentence_length"] > 0

    @pytest.mark.asyncio
    async def test_empty_text_with_no_content(self):
        ctx = FakePipelineContext(content=None, raw_input="")
        result = await hydrate_article_stats(ctx)

        assert result["char_count"] == 0
        assert result["paragraph_count"] == 0
        assert result["link_count"] == 0
        assert result["image_references"] == 0
        assert result["avg_sentence_length"] == 0.0
        assert result["has_links"] is False

    @pytest.mark.asyncio
    async def test_raw_input_used_when_content_none(self):
        raw = "This is raw input text with a link https://raw.example.com/data."
        ctx = FakePipelineContext(content=None, raw_input=raw)
        result = await hydrate_article_stats(ctx)

        assert result["char_count"] == len(raw)
        assert result["paragraph_count"] == 1
        assert result["link_count"] == 1
        assert result["has_links"] is True

    @pytest.mark.asyncio
    async def test_no_links_no_images(self):
        text = "A simple paragraph with no links or images.\n\nAnother paragraph here."
        ctx = FakePipelineContext(content=FakeContent(text=text))
        result = await hydrate_article_stats(ctx)

        assert result["char_count"] == len(text)
        assert result["paragraph_count"] == 2
        assert result["link_count"] == 0
        assert result["image_references"] == 0
        assert result["has_links"] is False

    @pytest.mark.asyncio
    async def test_chinese_text_sentence_splitting(self):
        text = "人工智能正在改变世界。机器学习是其核心技术！深度学习带来了革命？"
        ctx = FakePipelineContext(content=FakeContent(text=text))
        result = await hydrate_article_stats(ctx)

        assert result["char_count"] == len(text)
        assert result["paragraph_count"] == 1
        assert result["avg_sentence_length"] > 0
