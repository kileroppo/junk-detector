"""Tests for src/web/router.py — web UI helper functions and routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.web.router import _compute_stats


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestComputeStats:
    """Tests for _compute_stats helper."""

    def test_empty_records(self):
        """_compute_stats with empty list returns zeroes."""
        stats = _compute_stats([])

        assert stats["total"] == 0
        assert stats["avg_score"] == 0.0
        assert stats["junk_count"] == 0
        assert stats["high_quality_count"] == 0

    def test_single_record(self):
        """_compute_stats with one record computes correctly."""
        records = [{"overall_score": 50.0}]
        stats = _compute_stats(records)

        assert stats["total"] == 1
        assert stats["avg_score"] == 50.0
        assert stats["junk_count"] == 0
        assert stats["high_quality_count"] == 0

    def test_junk_count(self):
        """_compute_stats counts scores below 40 as junk."""
        records = [
            {"overall_score": 20.0},
            {"overall_score": 35.0},
            {"overall_score": 45.0},
        ]
        stats = _compute_stats(records)

        assert stats["junk_count"] == 2  # 20 and 35 are < 40

    def test_high_quality_count(self):
        """_compute_stats counts scores above 75 as high quality."""
        records = [
            {"overall_score": 80.0},
            {"overall_score": 90.0},
            {"overall_score": 50.0},
        ]
        stats = _compute_stats(records)

        assert stats["high_quality_count"] == 2  # 80 and 90 are > 75

    def test_average_score(self):
        """_compute_stats computes correct average."""
        records = [
            {"overall_score": 60.0},
            {"overall_score": 80.0},
        ]
        stats = _compute_stats(records)

        assert stats["avg_score"] == 70.0

    def test_mixed_records(self):
        """_compute_stats handles a mix of junk, medium, and high quality."""
        records = [
            {"overall_score": 10.0},  # junk
            {"overall_score": 50.0},  # medium
            {"overall_score": 90.0},  # high quality
        ]
        stats = _compute_stats(records)

        assert stats["total"] == 3
        assert stats["avg_score"] == 50.0
        assert stats["junk_count"] == 1
        assert stats["high_quality_count"] == 1


class TestWebRoutes:
    """Tests for web router page routes."""

    def test_index_redirects_to_dashboard(self, web_client):
        """GET / redirects to /dashboard."""
        response = web_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/dashboard" in response.headers["location"]

    @patch("src.web.router.get_history")
    def test_dashboard_page(self, mock_history, web_client):
        """GET /dashboard returns 200 HTML."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_score_form_page(self, web_client):
        """GET /score-form returns 200 HTML."""
        response = web_client.get("/score-form")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @patch("src.web.router.query")
    def test_history_page(self, mock_query, web_client):
        """GET /history-page returns 200 HTML."""
        mock_query.return_value = []
        response = web_client.get("/history-page")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @patch("src.web.router.query")
    def test_history_page_with_filters(self, mock_query, web_client):
        """GET /history-page with filter params passes them correctly."""
        mock_query.return_value = []
        response = web_client.get("/history-page?min_score=60&label=junk&page=2")
        assert response.status_code == 200

    def test_monitor_status_page(self, web_client):
        """GET /monitor-status returns 200 HTML."""
        response = web_client.get("/monitor-status")
        assert response.status_code == 200

    @patch("src.web.router.get_history")
    def test_partials_recent_scores(self, mock_history, web_client):
        """GET /partials/recent-scores returns HTML fragment."""
        mock_history.return_value = []
        response = web_client.get("/partials/recent-scores")
        assert response.status_code == 200

    def test_partials_monitor_stats(self, web_client):
        """GET /partials/monitor-stats returns HTML fragment."""
        response = web_client.get("/partials/monitor-stats")
        assert response.status_code == 200

    @patch("src.web.router.query")
    def test_result_detail_not_found(self, mock_query, web_client):
        """GET /result/{id} returns 404 for non-existent record."""
        mock_query.return_value = []
        response = web_client.get("/result/999")
        assert response.status_code == 404

    @patch("src.web.router.query")
    def test_result_detail_found(self, mock_query, web_client):
        """GET /result/{id} returns 200 for existing record."""
        mock_query.return_value = [
            {
                "id": 1,
                "overall_score": 72.5,
                "dimensions": {
                    "originality": 80,
                    "info_density": 70,
                    "reasoning_quality": 75,
                    "readability": 85,
                    "timeliness": 60,
                    "ai_generated_prob": 15,
                    "emotional_manipulation": 10,
                    "advertorial_prob": 20,
                    "scam_prob": 5,
                },
                "labels": [],
                "summary": "Good",
                "model_used": "test",
                "cost": 0.0,
                "confidence": 0.9,
                "scored_at": "2024-01-01T12:00:00",
                "title": "Test",
                "source_url": "https://example.com",
            }
        ]
        response = web_client.get("/result/1")
        assert response.status_code == 200


def _make_score_result():
    """Helper to create a ScoreResult for test mocks."""
    return ScoreResult(
        overall_score=72.5,
        dimensions=DimensionScores(
            originality=80,
            info_density=70,
            reasoning_quality=75,
            readability=85,
            timeliness=60,
            ai_generated_prob=15,
            emotional_manipulation=10,
            advertorial_prob=20,
            scam_prob=5,
        ),
        labels=[],
        summary="Good content",
        confidence=0.9,
        model_used="test",
        cost=0.001,
    )


def _make_content(text="extracted text", title="Title", source_url="https://example.com"):
    """Helper to create a Content object for test mocks."""
    return Content(
        input_type=InputType.TEXT,
        text=text,
        title=title,
        source_url=source_url,
    )


class TestScoreSubmit:
    """Tests for POST /score-submit endpoint."""

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_submit_text_input(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """POST /score-submit with text input returns 200 with result."""
        mock_extract.return_value = _make_content()
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "Some sample text for scoring"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        mock_score.assert_called_once()

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_submit_url_input(
        self, mock_extract_url, mock_save, mock_score, web_client
    ):
        """POST /score-submit with url input calls extract_from_url."""
        mock_extract_url.return_value = _make_content(
            text="web page content", source_url="https://example.com/article"
        )
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "url", "url": "https://example.com/article"},
        )

        assert response.status_code == 200
        mock_extract_url.assert_called_once_with("https://example.com/article")
        mock_score.assert_called_once()

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    def test_submit_text_looks_like_url(
        self, mock_extract_url, mock_save, mock_score, web_client
    ):
        """POST /score-submit with text starting with http:// calls extract_from_url."""
        mock_extract_url.return_value = _make_content(
            text="page content", source_url="http://example.com/page"
        )
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "http://example.com/page"},
        )

        assert response.status_code == 200
        mock_extract_url.assert_called_once_with("http://example.com/page")

    def test_submit_empty_input(self, web_client):
        """POST /score-submit with no text or url returns 422."""
        response = web_client.post(
            "/score-submit",
            data={"input_type": "text"},
        )

        assert response.status_code == 422
        assert "text/html" in response.headers["content-type"]

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    def test_submit_scorer_raises_exception(
        self, mock_extract, mock_score, web_client
    ):
        """POST /score-submit returns 500 when scorer raises."""
        mock_extract.return_value = _make_content()
        mock_score.side_effect = RuntimeError("LLM API error")

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "Some text to score"},
        )

        assert response.status_code == 500
        assert "text/html" in response.headers["content-type"]

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_submit_htmx_request(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """POST /score-submit with HX-Request header returns inline template."""
        mock_extract.return_value = _make_content()
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "Some text"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestResultDetailEdgeCases:
    """Edge case tests for GET /result/{id}."""

    @patch("src.web.router.query")
    def test_result_detail_query_raises(self, mock_query, web_client):
        """GET /result/{id} returns 404 when query() raises exception."""
        mock_query.side_effect = RuntimeError("DB connection error")

        response = web_client.get("/result/1")

        assert response.status_code == 404


class TestHistoryPageFilters:
    """Tests for GET /history-page with filters and pagination."""

    @patch("src.web.router.query")
    def test_history_page_date_from_filter(self, mock_query, web_client):
        """GET /history-page with date_from filter passes it to query."""
        mock_query.return_value = []

        response = web_client.get("/history-page?date_from=2024-01-01")

        assert response.status_code == 200
        # Verify date_from was passed in filters
        call_args = mock_query.call_args
        assert call_args[1]["filters"]["date_from"] == "2024-01-01"

    @patch("src.web.router.query")
    def test_history_page_pagination_page2(self, mock_query, web_client):
        """GET /history-page?page=2 fetches enough results for pagination."""
        # Return 40 results so page 2 has data
        mock_query.return_value = [
            {"overall_score": 50.0, "id": i} for i in range(40)
        ]

        response = web_client.get("/history-page?page=2")

        assert response.status_code == 200
        # page=2 means offset_limit = 2*20 = 40
        call_args = mock_query.call_args
        assert call_args[1]["limit"] == 40
