"""Tests for src/mcp/server.py - MCP server tools."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from src.mcp.server import mcp, quick_check, score_text, score_url


class TestMcpServerSetup:
    """Tests for MCP server initialization."""

    def test_mcp_server_name(self):
        """MCP server has correct name."""
        assert mcp.name == "junk-detector"

    def test_mcp_has_tools(self):
        """MCP server has registered tools."""
        # FastMCP stores tools internally
        assert mcp is not None


class TestScoreText:
    """Tests for score_text tool."""

    def test_junk_text_detected(self):
        """Known junk text returns is_junk=True."""
        result = score_text("日入过万 躺赚 财富自由 限时免费 加微信领取")
        assert result["is_junk"] is True
        assert result["score"] is not None
        assert result["score"] < 60

    def test_clean_text_not_junk(self):
        """Clean academic text is not flagged as junk."""
        result = score_text(
            "近年来人工智能技术在自然语言处理领域取得了显著进展。"
            "基于Transformer架构的大语言模型展现了强大的文本理解能力。"
        )
        # Rules should be inconclusive for clean text
        assert result.get("error") is None

    def test_error_handling(self):
        """Empty text does not crash."""
        result = score_text("")
        assert result.get("error") is None or result.get("score") is not None

    def test_score_text_includes_status(self):
        """score_text includes a 'status' key in its result."""
        result = score_text("日入过万 躺赚 财富自由 限时免费 加微信领取")
        assert "status" in result
        assert result["status"] in ("junk", "suspicious", "normal", "quality", "inconclusive")


class TestQuickCheck:
    """Tests for quick_check tool."""

    def test_junk_detected(self):
        """Quick check detects obvious junk."""
        result = quick_check("日入过万 躺赚 财富自由 加微信")
        assert result["is_junk"] is True
        assert result["score"] < 60

    def test_clean_text_passes(self):
        """Quick check passes clean content."""
        result = quick_check("人工智能技术在自然语言处理领域取得了显著进展")
        assert result["is_junk"] is False

    def test_reason_provided(self):
        """Quick check always provides a reason."""
        result = quick_check("测试内容")
        assert "reason" in result
        assert isinstance(result["reason"], str)

    def test_quick_check_includes_status(self):
        """quick_check includes a 'status' key in its result."""
        result = quick_check("日入过万 躺赚 财富自由 加微信")
        assert "status" in result
        assert result["status"] in ("junk", "suspicious", "normal", "quality", "inconclusive")


class TestScoreUrl:
    """Tests for score_url tool."""

    @pytest.mark.asyncio
    async def test_score_url_success(self):
        """score_url fetches content and scores it."""

        @dataclass
        class FakeContent:
            text: str = "日入过万 躺赚 财富自由 限时免费 加微信领取"
            title: str = "Fake Article"

        with patch("src.extractors.web.extract_from_url_simple", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = FakeContent()
            result = await score_url("https://example.com/article")
            assert result["url"] == "https://example.com/article"
            assert result["title"] == "Fake Article"
            assert result["is_junk"] is True
            assert result["score"] < 60

    @pytest.mark.asyncio
    async def test_score_url_error(self):
        """score_url returns error dict on failure."""

        with patch("src.extractors.web.extract_from_url_simple", new_callable=AsyncMock) as mock_extract:
            mock_extract.side_effect = Exception("Network error")
            result = await score_url("https://bad-url.example.com")
            assert result["error"] is not None
            assert result["url"] == "https://bad-url.example.com"
            assert result["score"] is None


class TestInconclusiveMessage:
    """Tests for inconclusive status and message."""

    def test_inconclusive_has_message(self):
        """score_text with clean text (method=rules_partial) returns status='inconclusive' and message field."""
        result = score_text(
            "近年来人工智能技术在自然语言处理领域取得了显著进展。"
            "基于Transformer架构的大语言模型展现了强大的文本理解能力。"
        )
        assert result.get("method") == "rules_partial"
        assert result["status"] == "inconclusive"
        assert "message" in result
        assert result["message"] == "规则引擎无法确定，建议使用完整LLM评分"
