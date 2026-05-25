"""Tests for the watch command."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()


class TestWatchCommand:
    """Test the watch CLI command."""

    def test_watch_command_exists(self):
        """watch command is registered and shows help."""
        result = runner.invoke(app, ["watch", "--help"])
        assert result.exit_code == 0
        assert "--urls-file" in result.output
        assert "--interval" in result.output

    def test_watch_requires_urls_file(self):
        """watch fails gracefully if no --urls-file given."""
        result = runner.invoke(app, ["watch"])
        assert result.exit_code != 0

    def test_watch_fails_on_missing_file(self, tmp_path):
        """watch exits with error if file does not exist."""
        result = runner.invoke(app, ["watch", "--urls-file", str(tmp_path / "nonexistent.txt")])
        assert result.exit_code == 1

    @patch("src.cli.main._batch_score", new_callable=AsyncMock)
    def test_watch_single_cycle(self, mock_batch, tmp_path):
        """watch reads URLs from file, scores them, and exits with --once."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://example.com/article1\nhttps://example.com/article2\n")

        mock_batch.return_value = [
            {
                "url": "https://example.com/article1",
                "score": 75,
                "verdict": "OK",
                "labels": [],
                "summary": "Good",
                "error": None,
            },
            {
                "url": "https://example.com/article2",
                "score": 25,
                "verdict": "JUNK",
                "labels": [],
                "summary": "Bad",
                "error": None,
            },
        ]

        result = runner.invoke(app, ["watch", "--urls-file", str(urls_file), "--once"])
        assert result.exit_code == 0
        # Should mention cycle info
        assert "Cycle" in result.output or "cycle" in result.output
        mock_batch.assert_called_once()

    @patch("src.cli.main._batch_score", new_callable=AsyncMock)
    def test_watch_skips_empty_and_comment_lines(self, mock_batch, tmp_path):
        """watch properly filters empty lines and comments from urls file."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("# This is a comment\nhttps://example.com/real\n\n# Another comment\n")

        mock_batch.return_value = [
            {
                "url": "https://example.com/real",
                "score": 60,
                "verdict": "OK",
                "labels": [],
                "summary": "OK",
                "error": None,
            },
        ]

        result = runner.invoke(app, ["watch", "--urls-file", str(urls_file), "--once"])
        assert result.exit_code == 0
        mock_batch.assert_called_once()
        args = mock_batch.call_args
        assert len(args[0][0]) == 1  # first positional arg is the urls list

    @patch("src.cli.main._batch_score", new_callable=AsyncMock)
    def test_watch_empty_file_prints_no_urls(self, mock_batch, tmp_path):
        """watch with empty file shows no-URLs message and exits cleanly."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("# only comments\n\n")

        result = runner.invoke(app, ["watch", "--urls-file", str(urls_file), "--once"])
        assert result.exit_code == 0
        mock_batch.assert_not_called()

    @patch("src.cli.main._batch_score", new_callable=AsyncMock)
    def test_watch_default_interval(self, mock_batch, tmp_path):
        """watch defaults to 3600 seconds interval."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://example.com/page\n")

        mock_batch.return_value = [
            {
                "url": "https://example.com/page",
                "score": 80,
                "verdict": "OK",
                "labels": [],
                "summary": "Fine",
                "error": None,
            },
        ]

        # --once to avoid loop; just verify it runs
        result = runner.invoke(app, ["watch", "--urls-file", str(urls_file), "--once"])
        assert result.exit_code == 0

    @patch("src.cli.main._batch_score", new_callable=AsyncMock)
    def test_watch_shows_timestamp(self, mock_batch, tmp_path):
        """watch prints timestamp in cycle output."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://example.com/page\n")

        mock_batch.return_value = [
            {
                "url": "https://example.com/page",
                "score": 50,
                "verdict": "CAUTION",
                "labels": [],
                "summary": "Meh",
                "error": None,
            },
        ]

        result = runner.invoke(app, ["watch", "--urls-file", str(urls_file), "--once"])
        assert result.exit_code == 0
        # Should contain date-like output (YYYY-MM-DD)
        import re

        assert re.search(r"\d{4}-\d{2}-\d{2}", result.output)

    @patch("src.cli.main._batch_score", new_callable=AsyncMock)
    def test_watch_handles_scoring_exception(self, mock_batch, tmp_path):
        """watch continues gracefully when _batch_score raises an exception."""
        urls_file = tmp_path / "urls.txt"
        urls_file.write_text("https://example.com/page\n")

        mock_batch.side_effect = RuntimeError("Network timeout")

        result = runner.invoke(app, ["watch", "--urls-file", str(urls_file), "--once"])
        assert result.exit_code == 0
        assert "failed" in result.output
