"""Integration tests for the CLI score command using typer.testing.CliRunner.

All LLM/scorer calls are mocked to avoid real API calls.
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from src.cli.main import app
from src.models.score import DimensionScores, ScoreResult

runner = CliRunner()


def _mock_score_result() -> ScoreResult:
    """Create a mock ScoreResult for testing."""
    return ScoreResult(
        overall_score=65.0,
        dimensions=DimensionScores(
            originality=70,
            info_density=60,
            reasoning_quality=65,
            readability=80,
            timeliness=50,
            ai_generated_prob=20,
            emotional_manipulation=15,
            advertorial_prob=10,
            scam_prob=5,
        ),
        labels=["高质量原创"],
        summary="Test summary",
        confidence=0.85,
        model_used="test-model",
        cost=0.001,
        rule_hits=[],
    )


class TestScorePrettyOutput:
    """Test pretty output format for score command."""

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    def test_score_text_pretty_output(self, mock_db_save, mock_scorer):
        """score --text with mocked scorer returns pretty output with key fields."""
        mock_scorer.return_value = _mock_score_result()
        mock_db_save.return_value = None

        result = runner.invoke(
            app, ["score", "--text", "sample text"], env={"DEEPSEEK_API_KEY": "test-key"}
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "鉴真评分" in result.output
        assert "综合评分" in result.output
        assert "原创性" in result.output
        assert "信息密度" in result.output
        assert "论证质量" in result.output
        assert "可读性" in result.output
        assert "AI生成概率" in result.output


class TestScoreJsonOutput:
    """Test JSON output format for score command."""

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    def test_score_text_json_output(self, mock_db_save, mock_scorer):
        """score --text --json outputs valid JSON with expected keys."""
        mock_scorer.return_value = _mock_score_result()
        mock_db_save.return_value = None

        result = runner.invoke(
            app, ["score", "--text", "sample text", "--json"], env={"DEEPSEEK_API_KEY": "test-key"}
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert "overall_score" in data
        assert "dimensions" in data
        assert "labels" in data
        assert "title" in data
        assert "source" in data
        assert data["overall_score"] == 65.0
        assert data["labels"] == ["高质量原创"]


class TestScoreInputValidation:
    """Test input validation for score command."""

    def test_score_no_input_error(self):
        """score with no options returns exit code 1 with error message."""
        result = runner.invoke(app, ["score"])

        assert result.exit_code == 1
        assert "--text" in result.output or "必须指定" in result.output

    def test_score_multiple_inputs_error(self):
        """score with multiple inputs returns exit code 1 with error message."""
        result = runner.invoke(app, ["score", "--text", "x", "--url", "http://x"])

        assert result.exit_code == 1
        assert "只能指定" in result.output or "一个" in result.output


class TestNoArgsShowsDemo:
    """Test that running with no arguments shows the demo."""

    def test_no_args_shows_demo(self):
        """Running junk-detector with no subcommand shows demo output, not --help."""
        result = runner.invoke(app, [])

        assert result.exit_code == 0, f"Output: {result.output}"
        # Demo output should contain scoring-related content
        assert "鉴真" in result.output or "评分" in result.output or "演示" in result.output
        # Should NOT just be the --help text
        assert "--help" not in result.output or "演示" in result.output


class TestScoreErrorHandling:
    """Test error handling scenarios for score command."""

    @patch("src.extractors.web.extract_from_url_simple", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_score_url_timeout_error(self, mock_extract, mock_simple):
        """score --url with TimeoutError shows graceful error message."""
        mock_extract.side_effect = TimeoutError("Connection timed out")
        mock_simple.side_effect = TimeoutError("Connection timed out")

        result = runner.invoke(
            app, ["score", "--url", "http://example.com"], env={"DEEPSEEK_API_KEY": "test-key"}
        )

        assert result.exit_code == 1
        assert "提取内容失败" in result.output

    def test_score_file_not_found(self):
        """score --file with nonexistent file shows file not found error."""
        result = runner.invoke(
            app, ["score", "--file", "/nonexistent/file.txt"], env={"DEEPSEEK_API_KEY": "test-key"}
        )

        assert result.exit_code == 1
        assert "提取内容失败" in result.output or "File not found" in result.output


class TestScoreApiKeyValidation:
    """Test API key validation for score command."""

    def test_score_missing_api_key_error(self):
        """score --text when DEEPSEEK_API_KEY is missing shows actionable error."""
        # Ensure no API key is set
        env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
        env["DEEPSEEK_API_KEY"] = ""

        result = runner.invoke(app, ["score", "--text", "sample"], env=env)

        assert result.exit_code == 1
        assert "DEEPSEEK_API_KEY" in result.output
        assert "not set" in result.output or "export" in result.output

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    def test_score_with_ollama_model_no_key_needed(self, mock_db_save, mock_scorer):
        """score --text --model ollama works without API key."""
        mock_scorer.return_value = _mock_score_result()
        mock_db_save.return_value = None

        # No API keys in environment
        env = {k: v for k, v in os.environ.items() if "API_KEY" not in k}

        result = runner.invoke(app, ["score", "--text", "sample", "--model", "ollama"], env=env)

        assert result.exit_code == 0, f"Output: {result.output}"

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.core.config.load_config")
    def test_score_unknown_model_warns(self, mock_load_config, mock_db_save, mock_scorer):
        """score --text with unknown model shows warning but still attempts scoring."""
        from src.models.score import ScoringConfig

        mock_scorer.return_value = _mock_score_result()
        mock_db_save.return_value = None
        mock_load_config.return_value = ScoringConfig(
            primary_model="mistral-large",
            fallback_model="mistral-large",
            confidence_threshold=0.7,
        )

        # No API keys needed since the model is unknown
        env = {k: v for k, v in os.environ.items() if "API_KEY" not in k}

        result = runner.invoke(
            app, ["score", "--text", "sample", "--model", "mistral-large"], env=env
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "Unknown model provider" in result.output
        assert "mistral-large" in result.output
