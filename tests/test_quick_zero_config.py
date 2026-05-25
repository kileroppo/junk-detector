"""Tests for quick command zero-config features: auto rules-only, stdin, exit codes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from src.cli.main import app
from src.models.score import FastScoreResult

runner = CliRunner()

# Obvious scam content with 5+ scam keywords + emotional + advertorial triggers
SCAM_CONTENT = "\u65e5\u5165\u8fc7\u4e07 \u8eba\u8d5a \u8d22\u5bcc\u81ea\u7531 \u9650\u65f6\u514d\u8d39 \u52a0\u5fae\u4fe1\u9886\u53d6!!! \u9707\u60ca! \u518d\u4e0d\u4e70\u5c31\u665a\u4e86!! \u4f18\u60e0\u5238 \u6298\u6263\u7801 \u70b9\u51fb\u94fe\u63a5"


def _mock_fast_result(quick_verdict: float = 75.0) -> FastScoreResult:
    """Create a mock FastScoreResult with configurable quick_verdict."""
    return FastScoreResult(
        quick_verdict=quick_verdict,
        scam_prob=10.0,
        advertorial_prob=15.0,
        emotional_manipulation=20.0,
        originality=80.0,
        summary="Test summary",
        confidence=0.85,
        model_used="test-model",
        cost=0.001,
    )


class TestAutoRulesOnlyNoApiKey:
    """Test auto rules-only when no API key is set."""

    def test_auto_rules_only_scam_no_api_key(self):
        """quick --text with scam content and no API key auto-engages rules-only."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_CONTENT, "--json"],
            env={"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )

        # Should succeed (no error message) with rules_only model
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        assert data["scam_prob"] >= 90.0
        # Exit code 1 because junk detected (score < 60)
        assert result.exit_code == 1

    def test_auto_rules_only_no_error_message(self):
        """Auto rules-only does not print any error or warning."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_CONTENT],
            env={"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )

        # No error symbol in output
        assert "\u274c" not in result.output
        # Verdict is shown
        assert "\U0001f6a8" in result.output or "\u26a0\ufe0f" in result.output


class TestStdinSupport:
    """Test stdin piping support for quick command."""

    def test_stdin_piped_scam_content(self):
        """Piped stdin with scam content is read and scored."""
        result = runner.invoke(
            app,
            ["quick", "--json"],
            input=SCAM_CONTENT,
            env={"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )

        # Should auto rules-only since no API key
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        assert data["scam_prob"] >= 90.0
        assert result.exit_code == 1

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_stdin_piped_with_api_key(self, mock_score_fast):
        """Piped stdin with API key uses LLM scoring."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick"],
            input="some text content",
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u2705" in result.output


class TestExitCodes:
    """Test exit code semantics for quick command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_exit_code_0_for_ok_content(self, mock_score_fast):
        """Exit code 0 when content scores >= 60 (OK)."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "good content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_exit_code_1_for_junk_content(self, mock_score_fast):
        """Exit code 1 when content scores < 60 (junk)."""
        mock_score_fast.return_value = _mock_fast_result(28.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "scam content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_exit_code_0_boundary_61(self, mock_score_fast):
        """Exit code 0 when content scores exactly 61 (>= 60)."""
        mock_score_fast.return_value = _mock_fast_result(61.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "decent content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_exit_code_1_boundary_59(self, mock_score_fast):
        """Exit code 1 when content scores exactly 59 (< 60)."""
        mock_score_fast.return_value = _mock_fast_result(59.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "mediocre content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_exit_code_1_boundary_60(self, mock_score_fast):
        """Exit code 0 when content scores exactly 60 (>= 60 is True)."""
        mock_score_fast.return_value = _mock_fast_result(60.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "borderline content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        # 60 >= 60 is True, so exit 0
        assert result.exit_code == 0

    def test_exit_code_2_for_no_input_tty(self):
        """Exit code 2 when no input provided and TTY (error)."""
        # CliRunner without input parameter simulates TTY
        result = runner.invoke(
            app,
            ["quick"],
        )

        assert result.exit_code == 2
        assert "\u5fc5\u987b\u6307\u5b9a" in result.output

    def test_exit_code_2_for_multiple_inputs(self):
        """Exit code 2 when multiple inputs provided."""
        result = runner.invoke(
            app,
            ["quick", "--text", "x", "--url", "http://x"],
        )

        assert result.exit_code == 2


class TestIntegrationNoApiKeyScam:
    """Integration: no API key + scam text -> auto rules-only -> exit 1."""

    def test_no_api_key_scam_auto_rules_only_exit_1(self):
        """No API key + scam text -> auto rules-only -> junk detected -> exit 1."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_CONTENT],
            env={"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )

        assert result.exit_code == 1
        assert "\U0001f6a8" in result.output
