"""End-to-end integration tests for the zero-config user experience.

Verifies that users can run junk-detector quick without any API keys set
and get meaningful results via the rules-only engine, stdin piping, and
correct exit codes.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from src.cli.main import app
from src.models.score import FastScoreResult

runner = CliRunner()

# Scam text that triggers multiple rules (scam + emotional + advertorial)
SCAM_TEXT = "日入过万 躺赚 财富自由 限时免费 加微信领取"

# Normal/clean text that rules cannot confidently classify
NORMAL_TEXT = "今天天气很好，我去公园散步了。"

# Environment with no API keys set
NO_API_KEYS_ENV = {
    "DEEPSEEK_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
}


class TestNoApiKeyAutoRulesOnly:
    """No API keys + scam text auto-engages rules-only mode with exit 1."""

    def test_scam_text_no_api_key_exit_1(self):
        """Running quick with scam text and no API keys uses rules-only and exits 1."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_TEXT],
            env=NO_API_KEYS_ENV,
        )

        # Should not show error message - auto rules-only engaged silently
        assert "❌" not in result.output
        # Exit code 1 means junk detected (score < 60)
        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}. Output: {result.output}"

    def test_scam_text_no_api_key_json_output(self):
        """No API keys + scam text + --json shows rules_only model and low verdict."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_TEXT, "--json"],
            env=NO_API_KEYS_ENV,
        )

        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}. Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        assert data["quick_verdict"] < 60

    def test_normal_text_no_api_key_exit_1_uncertain(self):
        """No API keys + normal text -> rules uncertain -> score=50 -> exit 1."""
        result = runner.invoke(
            app,
            ["quick", "--text", NORMAL_TEXT],
            env=NO_API_KEYS_ENV,
        )

        # Should not show error message
        assert "❌" not in result.output
        # Score 50 < 60 threshold, so exit code is 1
        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}. Output: {result.output}"


class TestStdinPiping:
    """stdin piping with scam text auto-engages rules-only and produces junk verdict."""

    def test_stdin_scam_text_exit_1(self):
        """Piping scam text via stdin (no --text flag) produces exit code 1."""
        result = runner.invoke(
            app,
            ["quick"],
            input=SCAM_TEXT,
            env=NO_API_KEYS_ENV,
        )

        assert "❌" not in result.output
        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}. Output: {result.output}"

    def test_stdin_scam_text_json(self):
        """Piping scam text via stdin with --json returns valid JSON with rules_only."""
        result = runner.invoke(
            app,
            ["quick", "--json"],
            input=SCAM_TEXT,
            env=NO_API_KEYS_ENV,
        )

        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}. Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        assert data["quick_verdict"] < 60


class TestExitCodeBoundary:
    """Exit code boundary: score >= 60 exits 0, score < 60 exits 1."""

    @patch("src.core.fast_scorer.score_fast")
    def test_score_exactly_60_exits_0(self, mock_score_fast):
        """Score of exactly 60 should produce exit code 0 (content OK)."""

        async def _return_60(*args, **kwargs):
            return FastScoreResult(
                quick_verdict=60.0,
                scam_prob=20.0,
                advertorial_prob=20.0,
                emotional_manipulation=20.0,
                originality=70.0,
                summary="Borderline OK",
                confidence=0.8,
                model_used="test-model",
            )

        mock_score_fast.side_effect = _return_60

        result = runner.invoke(
            app,
            ["quick", "--text", "some content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Expected exit 0, got {result.exit_code}. Output: {result.output}"

    @patch("src.core.fast_scorer.score_fast")
    def test_score_59_exits_1(self, mock_score_fast):
        """Score of 59 should produce exit code 1 (junk/suspicious)."""

        async def _return_59(*args, **kwargs):
            return FastScoreResult(
                quick_verdict=59.0,
                scam_prob=25.0,
                advertorial_prob=25.0,
                emotional_manipulation=25.0,
                originality=60.0,
                summary="Slightly suspicious",
                confidence=0.8,
                model_used="test-model",
            )

        mock_score_fast.side_effect = _return_59

        result = runner.invoke(
            app,
            ["quick", "--text", "some content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, f"Expected exit 1, got {result.exit_code}. Output: {result.output}"


class TestExitCode2ForErrors:
    """Exit code 2 for error conditions (no input in TTY mode)."""

    @patch("sys.stdin.isatty", return_value=True)
    def test_no_input_tty_exits_2(self, mock_isatty):
        """No input flags + TTY mode shows error and exits with code 2."""
        result = runner.invoke(
            app,
            ["quick"],
            env=NO_API_KEYS_ENV,
        )

        assert result.exit_code == 2, f"Expected exit 2, got {result.exit_code}. Output: {result.output}"
        assert "❌" in result.output
