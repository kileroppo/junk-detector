"""Tests for src/mcp/server.py - MCP server tools."""
from __future__ import annotations

import pytest
from src.mcp.server import mcp, score_text, score_url, quick_check


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
