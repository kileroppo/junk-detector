"""Tests for the CLI quick command and --fast flag on score command."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.models.score import FastScoreResult

runner = CliRunner()


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


class TestQuickCommandOK:
    """Test quick command with score > 60 (OK verdict)."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_ok_verdict(self, mock_score_fast):
        """quick --text with score > 60 shows OK emoji."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app, ["quick", "--text", "sample text"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u2705" in result.output
        assert "\u770b\u8d77\u6765\u6b63\u5e38" in result.output
        assert "75" in result.output


class TestQuickCommandJunk:
    """Test quick command with score < 40 (junk verdict)."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_junk_verdict(self, mock_score_fast):
        """quick --text with score < 40 shows junk emoji."""
        mock_score_fast.return_value = _mock_fast_result(28.0)

        result = runner.invoke(
            app, ["quick", "--text", "scam content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\U0001f6a8" in result.output
        assert "\u7591\u4f3c\u5783\u573e\u5185\u5bb9" in result.output
        assert "28" in result.output


class TestQuickCommandCaution:
    """Test quick command with 40 <= score <= 60 (caution verdict)."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_caution_verdict(self, mock_score_fast):
        """quick --text with 40 <= score <= 60 shows caution emoji."""
        mock_score_fast.return_value = _mock_fast_result(45.0)

        result = runner.invoke(
            app, ["quick", "--text", "mid quality"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u26a0\ufe0f" in result.output
        assert "\u9700\u8981\u6ce8\u610f" in result.output
        assert "45" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_boundary_40(self, mock_score_fast):
        """quick --text with score exactly 40 shows caution emoji."""
        mock_score_fast.return_value = _mock_fast_result(40.0)

        result = runner.invoke(
            app, ["quick", "--text", "boundary"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u26a0\ufe0f" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_boundary_60(self, mock_score_fast):
        """quick --text with score exactly 60 shows caution emoji."""
        mock_score_fast.return_value = _mock_fast_result(60.0)

        result = runner.invoke(
            app, ["quick", "--text", "boundary"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u26a0\ufe0f" in result.output


class TestQuickCommandJson:
    """Test --json flag on quick command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_json_output(self, mock_score_fast):
        """quick --text --json outputs valid JSON with expected keys."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app, ["quick", "--text", "sample", "--json"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert "quick_verdict" in data
        assert "scam_prob" in data
        assert "advertorial_prob" in data
        assert "emotional_manipulation" in data
        assert "originality" in data
        assert "summary" in data
        assert data["quick_verdict"] == 75.0


class TestQuickCommandValidation:
    """Test input validation for quick command."""

    def test_quick_no_input_error(self):
        """quick with no options returns exit code 1."""
        result = runner.invoke(app, ["quick"])

        assert result.exit_code == 1
        assert "\u5fc5\u987b\u6307\u5b9a" in result.output

    def test_quick_multiple_inputs_error(self):
        """quick with multiple inputs returns exit code 1."""
        result = runner.invoke(
            app, ["quick", "--text", "x", "--url", "http://x"],
        )

        assert result.exit_code == 1
        assert "\u53ea\u80fd\u6307\u5b9a" in result.output


class TestScoreFastFlag:
    """Test --fast flag on score command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_score_fast_flag_uses_fast_path(self, mock_score_fast):
        """score --fast --text uses the fast scoring path."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app, ["score", "--fast", "--text", "sample text"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_score_fast.assert_called_once()
        assert "\u2705" in result.output
        assert "75" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_score_fast_flag_json_output(self, mock_score_fast):
        """score --fast --text --json outputs JSON."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app, ["score", "--fast", "--text", "sample", "--json"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["quick_verdict"] == 75.0

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_score_fast_flag_junk_verdict(self, mock_score_fast):
        """score --fast --text with score < 40 shows junk emoji."""
        mock_score_fast.return_value = _mock_fast_result(25.0)

        result = runner.invoke(
            app, ["score", "--fast", "--text", "scam"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\U0001f6a8" in result.output

    def test_score_fast_no_input_error(self):
        """score --fast with no text/url/file returns exit code 1."""
        result = runner.invoke(app, ["score", "--fast"])

        assert result.exit_code == 1
        assert "\u5fc5\u987b\u6307\u5b9a" in result.output
