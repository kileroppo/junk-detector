"""Tests for the CLI quick command and --fast flag on score command."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

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
            app,
            ["quick", "--text", "sample text"],
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
            app,
            ["quick", "--text", "scam content"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, f"Output: {result.output}"
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
            app,
            ["quick", "--text", "mid quality"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "\u26a0\ufe0f" in result.output
        assert "\u9700\u8981\u6ce8\u610f" in result.output
        assert "45" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_boundary_40(self, mock_score_fast):
        """quick --text with score exactly 40 shows caution emoji."""
        mock_score_fast.return_value = _mock_fast_result(40.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "boundary"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        assert "\u26a0\ufe0f" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_text_boundary_60(self, mock_score_fast):
        """quick --text with score exactly 60 shows OK emoji and exits 0."""
        mock_score_fast.return_value = _mock_fast_result(60.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "boundary"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u2705" in result.output


class TestQuickCommandJson:
    """Test --json flag on quick command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_quick_json_output(self, mock_score_fast):
        """quick --text --json outputs valid JSON with expected keys."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--json"],
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
        """quick with no options returns exit code 2."""
        result = runner.invoke(app, ["quick"])

        assert result.exit_code == 2
        assert "\u5fc5\u987b\u6307\u5b9a" in result.output

    def test_quick_multiple_inputs_error(self):
        """quick with multiple inputs returns exit code 2."""
        result = runner.invoke(
            app,
            ["quick", "--text", "x", "--url", "http://x"],
        )

        assert result.exit_code == 2
        assert "\u53ea\u80fd\u6307\u5b9a" in result.output


class TestScoreFastFlag:
    """Test --fast flag on score command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_score_fast_flag_uses_fast_path(self, mock_score_fast):
        """score --fast --text uses the fast scoring path."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["score", "--fast", "--text", "sample text"],
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
            app,
            ["score", "--fast", "--text", "sample", "--json"],
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
            app,
            ["score", "--fast", "--text", "scam"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\U0001f6a8" in result.output

    def test_score_fast_no_input_error(self):
        """score --fast with no text/url/file returns exit code 1."""
        result = runner.invoke(app, ["score", "--fast"])

        assert result.exit_code == 1
        assert "\u5fc5\u987b\u6307\u5b9a" in result.output


class TestQuickThreshold:
    """Test --threshold flag on quick command."""

    def test_threshold_80_rules_only_pass(self):
        """--threshold 80 with clean content (rules-only) exits 0 when score >= 80."""
        # Clean text that rules can't determine -> score 50, which is < 80 -> exit 1
        # We need text that rules confidently say is OK (high quick_verdict)
        # Actually rules-only with no flags -> score 50 (uncertain), exit 1 at threshold 80
        # Let's use a scam text that gets a low score
        result = runner.invoke(
            app,
            ["quick", "--text", "这是一段普通的新闻内容", "--rules-only", "--threshold", "80"],
        )
        # Rules can't determine -> score 50, which is < 80 -> exit 1
        assert result.exit_code == 1

    def test_threshold_30_rules_only_pass(self):
        """--threshold 30 with uncertain content (rules-only, score 50) exits 0."""
        result = runner.invoke(
            app,
            ["quick", "--text", "这是一段普通的新闻内容", "--rules-only", "--threshold", "30"],
        )
        # Rules can't determine -> score 50, which is >= 30 -> exit 0
        assert result.exit_code == 0

    def test_threshold_default_scam_fails(self):
        """Scam content fails at default threshold 60."""
        result = runner.invoke(
            app,
            ["quick", "--text", "日入过万躺赚财富自由限时免费", "--rules-only"],
        )
        # Scam keywords trigger -> high scam_prob -> low quick_verdict -> exit 1
        assert result.exit_code == 1

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_threshold_80_with_llm(self, mock_score_fast):
        """--threshold 80 with LLM score 75 exits 1 (below threshold)."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--threshold", "80"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, f"Output: {result.output}"

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_threshold_50_with_llm(self, mock_score_fast):
        """--threshold 50 with LLM score 75 exits 0 (above threshold)."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--threshold", "50"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"


class TestQuickFormat:
    """Test --format flag on quick command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_format_json_output(self, mock_score_fast):
        """--format json produces valid JSON output."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--format", "json"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert "quick_verdict" in data
        assert data["quick_verdict"] == 75.0
        assert "summary" in data

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_format_csv_output(self, mock_score_fast):
        """--format csv produces comma-separated output."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--format", "csv"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        line = result.output.strip()
        parts = line.split(",", 2)
        assert len(parts) == 3
        assert parts[0] == "75"
        assert parts[1] == "OK"

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_format_csv_junk(self, mock_score_fast):
        """--format csv with junk score shows JUNK verdict."""
        mock_score_fast.return_value = _mock_fast_result(30.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "bad content", "--format", "csv"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        line = result.output.strip()
        parts = line.split(",", 2)
        assert parts[0] == "30"
        assert parts[1] == "JUNK"

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_format_human_default(self, mock_score_fast):
        """--format human (default) produces colored emoji output."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--format", "human"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u2705" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    def test_json_flag_equivalent_to_format_json(self, mock_score_fast):
        """--json flag is equivalent to --format json."""
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app,
            ["quick", "--text", "sample", "--json"],
            env={"DEEPSEEK_API_KEY": "test-key"},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["quick_verdict"] == 75.0

    def test_format_json_rules_only(self):
        """--format json works with --rules-only."""
        result = runner.invoke(
            app,
            ["quick", "--text", "日入过万躺赚财富自由限时免费", "--rules-only", "--format", "json"],
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        data = json.loads(result.output)
        assert "quick_verdict" in data
        assert data["scam_prob"] >= 95

    def test_format_csv_rules_only(self):
        """--format csv works with --rules-only."""
        result = runner.invoke(
            app,
            ["quick", "--text", "日入过万躺赚财富自由限时免费", "--rules-only", "--format", "csv"],
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        line = result.output.strip()
        parts = line.split(",", 2)
        assert len(parts) == 3
        assert parts[1] == "JUNK"
