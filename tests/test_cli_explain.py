"""Tests for the interactive explain command."""

from __future__ import annotations

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
