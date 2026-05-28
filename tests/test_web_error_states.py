"""Tests for web UI error handling and edge cases.

Covers error responses, invalid inputs, HTMX error fragments,
and graceful degradation under failure conditions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestScoreSubmitErrors:
    """Tests for POST /score-submit error handling."""

    def test_submit_no_text_no_url(self, web_client):
        """POST /score-submit with no text and no url returns 422 HTML error."""
        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": ""},
        )

        assert response.status_code == 422
        assert "text/html" in response.headers["content-type"]

    def test_submit_empty_fields(self, web_client):
        """POST /score-submit with empty input_type returns 422."""
        response = web_client.post(
            "/score-submit",
            data={"input_type": "text"},
        )

        assert response.status_code == 422
        assert "text/html" in response.headers["content-type"]

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    def test_submit_scorer_raises_returns_500_with_message(
        self, mock_extract, mock_score, web_client
    ):
        """POST /score-submit returns 500 HTML with generic error message."""
        from src.models.score import Content, InputType

        mock_extract.return_value = Content(
            input_type=InputType.TEXT,
            text="test content",
            title="Test",
            source_url=None,
        )
        mock_score.side_effect = RuntimeError("API rate limit exceeded")

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "Some text to score"},
        )

        assert response.status_code == 500
        assert "text/html" in response.headers["content-type"]
        assert "评分失败，请稍后重试" in response.text
        # Raw error message should NOT leak to user
        assert "API rate limit exceeded" not in response.text

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    def test_submit_htmx_error_returns_fragment(
        self, mock_extract, mock_score, web_client
    ):
        """HTMX score-submit error returns HTML fragment, not full page."""
        from src.models.score import Content, InputType

        mock_extract.return_value = Content(
            input_type=InputType.TEXT,
            text="test content",
            title="Test",
            source_url=None,
        )
        mock_score.side_effect = RuntimeError("Connection timeout")

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "Some text"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 500
        assert "text/html" in response.headers["content-type"]
        assert "评分失败，请稍后重试" in response.text
        # Raw error message should NOT leak to user
        assert "Connection timeout" not in response.text
        # Should be a fragment (div), not a full HTML page
        assert "<!DOCTYPE html>" not in response.text

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_submit_url_extraction_fails(
        self, mock_extract_url, mock_score, web_client
    ):
        """POST /score-submit with URL extraction failure returns 500."""
        mock_extract_url.side_effect = RuntimeError("Failed to fetch URL")

        response = web_client.post(
            "/score-submit",
            data={"input_type": "url", "url": "https://invalid.example.com/page"},
        )

        assert response.status_code == 500
        assert "text/html" in response.headers["content-type"]
        assert "评分失败，请稍后重试" in response.text
        # Raw error message should NOT leak to user
        assert "Failed to fetch URL" not in response.text


class TestResultDetailErrors:
    """Tests for GET /result/{id} error handling."""

    @patch("src.storage.db.get_by_id")
    def test_result_nonexistent_id_returns_404(self, mock_get_by_id, web_client):
        """GET /result/999999 returns 404."""
        mock_get_by_id.return_value = None

        response = web_client.get("/result/999999")

        assert response.status_code == 404

    @patch("src.storage.db.get_by_id")
    def test_result_query_exception_returns_404(self, mock_get_by_id, web_client):
        """GET /result/{id} returns 404 when database query raises."""
        mock_get_by_id.side_effect = RuntimeError("Database error")

        response = web_client.get("/result/1")

        assert response.status_code == 404


class TestHistoryFilterCombinations:
    """Tests for history page with various filter combinations."""

    @patch("src.web.routes.pages.query")
    def test_history_min_score_filter(self, mock_query, web_client):
        """GET /history-page?min_score=60 passes filter to query."""
        mock_query.return_value = []

        response = web_client.get("/history-page?min_score=60")

        assert response.status_code == 200
        call_args = mock_query.call_args
        assert call_args[1]["filters"]["min_score"] == 60.0

    @patch("src.web.routes.pages.query")
    def test_history_label_filter(self, mock_query, web_client):
        """GET /history-page?label=junk passes filter to query."""
        mock_query.return_value = []

        response = web_client.get("/history-page?label=junk")

        assert response.status_code == 200
        call_args = mock_query.call_args
        assert call_args[1]["filters"]["label"] == "junk"

    @patch("src.web.routes.pages.query")
    def test_history_all_filters_combined(self, mock_query, web_client):
        """GET /history-page with all filters combined."""
        mock_query.return_value = []

        response = web_client.get(
            "/history-page?min_score=50&label=high&date_from=2024-06-01&page=1"
        )

        assert response.status_code == 200
        call_args = mock_query.call_args
        filters = call_args[1]["filters"]
        assert filters["min_score"] == 50.0
        assert filters["label"] == "high"
        assert filters["date_from"] == "2024-06-01"

    @patch("src.web.routes.pages.query")
    def test_history_zero_min_score_excluded(self, mock_query, web_client):
        """GET /history-page?min_score=0 excludes min_score from filters."""
        mock_query.return_value = []

        response = web_client.get("/history-page?min_score=0")

        assert response.status_code == 200
        call_args = mock_query.call_args
        # min_score=0 is excluded because condition is `min_score > 0`
        # When no filters are added, filters dict is empty/falsy -> passes None
        assert call_args[1]["filters"] is None

    @patch("src.web.routes.pages.query")
    def test_history_page_large_page_number(self, mock_query, web_client):
        """GET /history-page?page=999 with empty results returns 200."""
        mock_query.return_value = []

        response = web_client.get("/history-page?page=999")

        assert response.status_code == 200


class TestDashboardExceptionGraceful:
    """Tests for dashboard graceful degradation."""

    @patch("src.web.routes.pages.get_history")
    def test_dashboard_db_error_shows_zero_stats(self, mock_history, web_client):
        """Dashboard with DB error shows page with zero total."""
        mock_history.side_effect = Exception("Connection refused")

        response = web_client.get("/dashboard")

        assert response.status_code == 200
        html = response.text
        # Stats should show zeros
        assert "总评分数" in html
