"""Tests for the CLI batch command."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.models.score import Content, FastScoreResult, ScoreResult, DimensionScores

runner = CliRunner()


def _mock_content(url: str = "http://example.com") -> Content:
    """Create a mock Content object."""
    return Content(
        input_type="url",
        text="Test article content about technology",
        source_url=url,
        title="Test Article",
    )


def _mock_fast_result(quick_verdict: float = 75.0) -> FastScoreResult:
    """Create a mock FastScoreResult."""
    return FastScoreResult(
        quick_verdict=quick_verdict,
        scam_prob=10.0,
        advertorial_prob=15.0,
        emotional_manipulation=20.0,
        originality=80.0,
        summary="Good quality content",
        confidence=0.85,
        model_used="test-model",
        cost=0.001,
    )


def _mock_full_result(overall_score: float = 75.0) -> ScoreResult:
    """Create a mock ScoreResult for full scoring."""
    return ScoreResult(
        overall_score=overall_score,
        dimensions=DimensionScores(
            originality=80.0,
            info_density=70.0,
            reasoning_quality=75.0,
            readability=80.0,
            timeliness=60.0,
            ai_generated_prob=20.0,
            emotional_manipulation=15.0,
            advertorial_prob=10.0,
            scam_prob=5.0,
        ),
        labels=["informative"],
        summary="Well-written article",
        confidence=0.9,
        model_used="test-model",
        cost=0.002,
    )


class TestBatchWithUrlsFile:
    """Test batch command with --urls-file."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_urls_file_basic(self, mock_extract, mock_score_fast):
        """batch --urls-file scores all URLs and shows table."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.return_value = _mock_fast_result(75.0)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://example.com/1\nhttp://example.com/2\nhttp://example.com/3\n")
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(app, ["batch", "--urls-file", tmp_path])
            assert result.exit_code == 0, f"Output: {result.output}"
            assert "example.com/1" in result.output
            assert "example.com/2" in result.output
            assert "example.com/3" in result.output
            assert "\u5171 3 \u7bc7" in result.output
            assert mock_extract.call_count == 3
            assert mock_score_fast.call_count == 3
        finally:
            Path(tmp_path).unlink()

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_urls_file_shows_scores(self, mock_extract, mock_score_fast):
        """batch shows scores and verdict in table output."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.return_value = _mock_fast_result(75.0)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://example.com/article\n")
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(app, ["batch", "--urls-file", tmp_path])
            assert result.exit_code == 0, f"Output: {result.output}"
            assert "75" in result.output
            assert "\u2705" in result.output  # OK verdict emoji
        finally:
            Path(tmp_path).unlink()


class TestBatchWithStdin:
    """Test batch command with --stdin."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_stdin_basic(self, mock_extract, mock_score_fast):
        """batch --stdin reads URLs from stdin."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.return_value = _mock_fast_result(65.0)

        result = runner.invoke(
            app, ["batch", "--stdin"],
            input="http://example.com/a\nhttp://example.com/b\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "example.com/a" in result.output
        assert "example.com/b" in result.output
        assert mock_extract.call_count == 2

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_stdin_with_json(self, mock_extract, mock_score_fast):
        """batch --stdin --json outputs JSON."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.return_value = _mock_fast_result(73.0)

        result = runner.invoke(
            app, ["batch", "--stdin", "--json"],
            input="http://example.com/test\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["url"] == "http://example.com/test"
        assert data[0]["score"] == 73.0
        assert data[0]["verdict"] == "OK"


class TestBatchErrorHandling:
    """Test error handling in batch command."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url_simple", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_one_url_fails_extraction(self, mock_extract, mock_simple, mock_score_fast):
        """When one URL fails extraction (both primary and fallback), show ERROR and continue."""
        mock_extract.side_effect = [
            _mock_content(),
            Exception("Connection timeout"),
            _mock_content(),
        ]
        mock_simple.side_effect = Exception("Simple also failed")
        mock_score_fast.return_value = _mock_fast_result(75.0)

        result = runner.invoke(
            app, ["batch", "--stdin"],
            input="http://ok.com/1\nhttp://fail.com/2\nhttp://ok.com/3\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u5931\u8d25" in result.output  # "失败" in error row
        assert "\u5171 3 \u7bc7" in result.output  # Still shows all 3

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_scoring_fails(self, mock_extract, mock_score_fast):
        """When scoring fails for a URL, show ERROR and continue."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.side_effect = [
            _mock_fast_result(80.0),
            Exception("LLM rate limit"),
        ]

        result = runner.invoke(
            app, ["batch", "--stdin"],
            input="http://example.com/1\nhttp://example.com/2\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\u5171 2 \u7bc7" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url_simple", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_error_in_json_output(self, mock_extract, mock_simple, mock_score_fast):
        """JSON output shows ERROR verdict for failed URLs."""
        mock_extract.side_effect = Exception("timeout")
        mock_simple.side_effect = Exception("simple also timed out")

        result = runner.invoke(
            app, ["batch", "--stdin", "--json"],
            input="http://fail.com/page\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data[0]["verdict"] == "ERROR"
        assert data[0]["score"] is None
        assert "timeout" in data[0]["error"]


class TestBatchJsonOutput:
    """Test --json output format."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_json_format(self, mock_extract, mock_score_fast):
        """JSON output has correct structure."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.return_value = _mock_fast_result(50.0)

        result = runner.invoke(
            app, ["batch", "--stdin", "--json"],
            input="http://example.com/article\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1

        item = data[0]
        assert "url" in item
        assert "score" in item
        assert "verdict" in item
        assert "labels" in item
        assert "summary" in item
        assert item["score"] == 50.0
        assert item["verdict"] == "CAUTION"
        assert item["summary"] == "Good quality content"

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_json_multiple_urls(self, mock_extract, mock_score_fast):
        """JSON output includes all scored URLs."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.side_effect = [
            _mock_fast_result(80.0),
            _mock_fast_result(30.0),
            _mock_fast_result(50.0),
        ]

        result = runner.invoke(
            app, ["batch", "--stdin", "--json"],
            input="http://a.com\nhttp://b.com\nhttp://c.com\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["verdict"] == "OK"
        assert data[1]["verdict"] == "JUNK"
        assert data[2]["verdict"] == "CAUTION"


class TestBatchInputValidation:
    """Test input validation for batch command."""

    def test_batch_no_input_error(self):
        """batch with neither --urls-file nor --stdin returns error."""
        result = runner.invoke(app, ["batch"])

        assert result.exit_code == 1
        assert "\u5fc5\u987b\u6307\u5b9a" in result.output

    def test_batch_both_inputs_error(self):
        """batch with both --urls-file and --stdin returns error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("http://example.com\n")
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(app, ["batch", "--urls-file", tmp_path, "--stdin"])
            assert result.exit_code == 1
            assert "\u53ea\u80fd\u6307\u5b9a" in result.output
        finally:
            Path(tmp_path).unlink()

    def test_batch_file_not_found(self):
        """batch with non-existent file returns error."""
        result = runner.invoke(app, ["batch", "--urls-file", "/nonexistent/path.txt"])

        assert result.exit_code == 1
        assert "\u6587\u4ef6\u4e0d\u5b58\u5728" in result.output

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_empty_file(self, mock_extract, mock_score_fast):
        """batch with empty file shows no-results message."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(app, ["batch", "--urls-file", tmp_path])
            assert result.exit_code == 0, f"Output: {result.output}"
            assert "\u6ca1\u6709\u9700\u8981\u8bc4\u5206" in result.output
            mock_extract.assert_not_called()
        finally:
            Path(tmp_path).unlink()

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_comments_and_empty_lines_skipped(self, mock_extract, mock_score_fast):
        """batch skips comment lines and empty lines."""
        mock_extract.return_value = _mock_content()
        mock_score_fast.return_value = _mock_fast_result(70.0)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# This is a comment\n\nhttp://example.com/real\n\n# Another comment\n")
            f.flush()
            tmp_path = f.name

        try:
            result = runner.invoke(app, ["batch", "--urls-file", tmp_path])
            assert result.exit_code == 0, f"Output: {result.output}"
            assert mock_extract.call_count == 1
            assert "example.com/real" in result.output
        finally:
            Path(tmp_path).unlink()


class TestBatchFullScorer:
    """Test --fast=False uses full scorer."""

    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url_simple", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_fallback_to_simple_extraction(self, mock_extract, mock_simple, mock_score_fast):
        """When primary extraction fails, batch should fall back to simple extraction."""
        fallback_content = _mock_content("http://example.com/fallback")
        mock_extract.side_effect = Exception("Primary extractor failed")
        mock_simple.return_value = fallback_content
        mock_score_fast.return_value = _mock_fast_result(70.0)

        result = runner.invoke(
            app, ["batch", "--stdin"],
            input="http://example.com/fallback\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        # The URL should be scored successfully via fallback
        mock_simple.assert_called_once_with("http://example.com/fallback")
        mock_score_fast.assert_called_once()
        # Should NOT show ERROR since fallback succeeded
        assert "ERROR" not in result.output.upper() or "\u5931\u8d25" not in result.output

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_no_fast_uses_full_scorer(self, mock_extract, mock_score):
        """batch --no-fast uses the full 9-dimension scorer."""
        mock_extract.return_value = _mock_content()
        mock_score.return_value = _mock_full_result(75.0)

        result = runner.invoke(
            app, ["batch", "--stdin", "--no-fast"],
            input="http://example.com/article\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        mock_score.assert_called_once()
        assert "75" in result.output

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_batch_no_fast_json_output(self, mock_extract, mock_score):
        """batch --no-fast --json outputs correct JSON with labels."""
        mock_extract.return_value = _mock_content()
        mock_score.return_value = _mock_full_result(75.0)

        result = runner.invoke(
            app, ["batch", "--stdin", "--no-fast", "--json"],
            input="http://example.com/article\n",
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data[0]["labels"] == ["informative"]
        assert data[0]["summary"] == "Well-written article"
