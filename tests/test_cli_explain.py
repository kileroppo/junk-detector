"""Tests for the interactive explain command."""

from __future__ import annotations

import unittest.mock

from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()


class TestExplainCommand:
    """Test the explain command with --choice option (non-interactive mode)."""

    def test_explain_choice_1_dimensions(self):
        """explain --choice 1 returns info about scoring dimensions."""
        result = runner.invoke(app, ["explain", "--choice", "1"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "9个维度" in result.output
        assert "原创性" in result.output
        assert "信息密度" in result.output
        assert "综合评分越高" in result.output

    def test_explain_choice_2_rules_engine(self):
        """explain --choice 2 returns info about the rules engine."""
        result = runner.invoke(app, ["explain", "--choice", "2"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "规则引擎" in result.output
        assert "关键词匹配" in result.output
        assert "毫秒级响应" in result.output

    def test_explain_choice_3_why_flagged(self):
        """explain --choice 3 explains why content gets flagged."""
        result = runner.invoke(app, ["explain", "--choice", "3"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "风险关键词" in result.output
        assert "标记" in result.output
        # Rich may wrap long lines, so check without newlines
        output_flat = result.output.replace("\n", "")
        assert "评分结果中列出" in output_flat

    def test_explain_invalid_choice(self):
        """explain --choice with invalid number shows error."""
        result = runner.invoke(app, ["explain", "--choice", "5"])

        assert result.exit_code == 1
        assert "无效选择" in result.output

    def test_explain_choice_0_invalid(self):
        """explain --choice 0 is invalid."""
        result = runner.invoke(app, ["explain", "--choice", "0"])

        assert result.exit_code == 1
        assert "无效选择" in result.output

    def test_explain_non_interactive_prints_all(self):
        """When stdout is not a tty and --choice not provided, prints all Q&As."""
        with unittest.mock.patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            # CliRunner does not have a real tty, so the non-interactive path
            # is triggered by default (sys.stdout.isatty() is False)
            result = runner.invoke(app, ["explain"])

        assert result.exit_code == 0, f"Output: {result.output}"
        # Should contain all 3 answers without prompting
        output_flat = result.output.replace("\n", "")
        assert "9个维度" in output_flat or "9\u4e2a\u7ef4\u5ea6" in output_flat
        assert "规则引擎" in output_flat or "\u89c4\u5219\u5f15\u64ce" in output_flat
        assert "风险关键词" in output_flat or "\u98ce\u9669\u5173\u952e\u8bcd" in output_flat
