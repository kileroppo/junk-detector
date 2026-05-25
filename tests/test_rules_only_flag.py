"""Tests for --rules-only flag on quick and score commands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()

# Obvious scam content that triggers multiple rules (scam + emotional + advertorial)
SCAM_CONTENT = "\u65e5\u5165\u8fc7\u4e07 \u8eba\u8d5a \u8d22\u5bcc\u81ea\u7531 \u9650\u65f6\u514d\u8d39 \u52a0\u5fae\u4fe1\u9886\u53d6!!! \u9707\u60ca! \u518d\u4e0d\u4e70\u5c31\u665a\u4e86!! \u4f18\u60e0\u5238 \u6298\u6263\u7801 \u70b9\u51fb\u94fe\u63a5"

# Normal technical content that rules cannot determine
NORMAL_CONTENT = "normal technical content"


class TestQuickRulesOnlyScam:
    """Test quick --rules-only with scam content returns junk verdict."""

    def test_quick_rules_only_scam_text(self):
        """quick --rules-only --text with scam content returns junk verdict (exit 1)."""
        result = runner.invoke(
            app,
            ["quick", "--rules-only", "--text", SCAM_CONTENT],
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        # Should show junk verdict (score < 40)
        assert "\U0001f6a8" in result.output or "\u26a0\ufe0f" in result.output

    def test_quick_rules_only_short_flag(self):
        """quick -r --text with scam content works with short flag."""
        result = runner.invoke(
            app,
            ["quick", "-r", "--text", SCAM_CONTENT],
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "\U0001f6a8" in result.output


class TestQuickRulesOnlyNormal:
    """Test quick --rules-only with normal content returns uncertain verdict."""

    def test_quick_rules_only_normal_text(self):
        """quick --rules-only --text with normal content returns uncertain verdict."""
        result = runner.invoke(
            app,
            ["quick", "--rules-only", "--text", NORMAL_CONTENT],
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        # Should show caution/uncertain verdict (score 50 maps to caution)
        assert "\u26a0\ufe0f" in result.output


class TestScoreRulesOnlyJson:
    """Test score --rules-only --json returns valid JSON with model_used=rules_only."""

    def test_score_rules_only_scam_json(self):
        """score --rules-only --text --json with scam content returns valid JSON."""
        result = runner.invoke(
            app,
            ["score", "--rules-only", "--text", SCAM_CONTENT, "--json"],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        assert "quick_verdict" in data
        assert "scam_prob" in data
        assert "advertorial_prob" in data
        assert "emotional_manipulation" in data

    def test_score_rules_only_normal_json(self):
        """score --rules-only --text --json with normal content returns rules_only model."""
        result = runner.invoke(
            app,
            ["score", "--rules-only", "--text", NORMAL_CONTENT, "--json"],
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        # Should be uncertain (score 50)
        assert data["quick_verdict"] == 50.0

    def test_score_rules_only_no_api_key_needed(self):
        """score --rules-only works without any API key set."""
        result = runner.invoke(
            app,
            ["score", "--rules-only", "--text", SCAM_CONTENT, "--json"],
            env={"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
