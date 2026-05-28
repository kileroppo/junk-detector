"""Tests for FEAT-001: Core Experience + Performance features.

Tests SSE streaming endpoint, compare routes, simple mode template,
pagination with offset/limit, and count_records.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.score import Content, DimensionScores, InputType, ScoreResult
from src.storage.db import count_records, init_db, query, save


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


def _make_score_result(overall=72.5):
    """Helper to create a ScoreResult for test mocks."""
    return ScoreResult(
        overall_score=overall,
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
        labels=["高质量原创"],
        summary="Good content",
        confidence=0.9,
        model_used="test",
        cost=0.001,
    )


def _make_content(text="extracted text", title="Title", source_url=None):
    """Helper to create a Content object for test mocks."""
    return Content(
        input_type=InputType.TEXT,
        text=text,
        title=title,
        source_url=source_url,
    )


# ---------------------------------------------------------------------------
# SSE Streaming tests
# ---------------------------------------------------------------------------


class TestScoreStream:
    """Tests for POST /score-stream SSE endpoint."""

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    @patch("src.storage.db.save")
    def test_score_stream_returns_event_stream(
        self, mock_save, mock_extract, mock_score, web_client
    ):
        """POST /score-stream returns text/event-stream content type."""
        mock_extract.return_value = _make_content()
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-stream",
            data={"input_type": "text", "text": "Sample text for scoring"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    @patch("src.storage.db.save")
    def test_score_stream_has_rules_result_event(
        self, mock_save, mock_extract, mock_score, web_client
    ):
        """POST /score-stream emits rules_result event first."""
        mock_extract.return_value = _make_content()
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-stream",
            data={"input_type": "text", "text": "Sample text for scoring"},
        )

        body = response.text
        assert "event: rules_result" in body

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    @patch("src.storage.db.save")
    def test_score_stream_has_final_result_event(
        self, mock_save, mock_extract, mock_score, web_client
    ):
        """POST /score-stream emits final_result event after LLM."""
        mock_extract.return_value = _make_content()
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-stream",
            data={"input_type": "text", "text": "Sample text for scoring"},
        )

        body = response.text
        assert "event: final_result" in body

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.text.extract_from_text")
    @patch("src.storage.db.save")
    def test_score_stream_rules_result_contains_dimensions(
        self, mock_save, mock_extract, mock_score, web_client
    ):
        """rules_result event contains dimension data."""
        mock_extract.return_value = _make_content()
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-stream",
            data={"input_type": "text", "text": "Sample text for scoring"},
        )

        body = response.text
        assert "overall_score" in body
        assert "dimensions" in body

    def test_score_stream_empty_input_returns_error_event(self, web_client):
        """POST /score-stream with no input returns error event."""
        response = web_client.post(
            "/score-stream",
            data={"input_type": "text"},
        )

        assert response.status_code == 200
        assert "event: error" in response.text

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    def test_score_stream_url_input(
        self, mock_save, mock_extract_url, mock_score, web_client
    ):
        """POST /score-stream with url input works correctly."""
        mock_extract_url.return_value = _make_content(
            text="web content", source_url="https://example.com"
        )
        mock_score.return_value = _make_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-stream",
            data={"input_type": "url", "url": "https://example.com/article"},
        )

        assert response.status_code == 200
        assert "event: final_result" in response.text


# ---------------------------------------------------------------------------
# Compare page tests
# ---------------------------------------------------------------------------


class TestComparePage:
    """Tests for compare page routes."""

    def test_compare_page_returns_200(self, web_client):
        """GET /compare returns 200 HTML."""
        response = web_client.get("/compare")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "对比评分" in response.text

    def test_compare_page_has_two_textareas(self, web_client):
        """GET /compare page contains two text inputs."""
        response = web_client.get("/compare")
        assert "text_a" in response.text
        assert "text_b" in response.text

    def test_compare_submit_empty_input(self, web_client):
        """POST /compare-submit with empty input returns 422."""
        response = web_client.post(
            "/compare-submit",
            data={"text_a": "", "text_b": ""},
        )
        assert response.status_code == 422

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    def test_compare_submit_returns_results(self, mock_score, web_client):
        """POST /compare-submit with two texts returns comparison results."""
        mock_score.return_value = _make_score_result()

        response = web_client.post(
            "/compare-submit",
            data={"text_a": "First text content", "text_b": "Second text content"},
        )

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Should contain both result sections
        assert "文本 A" in response.text
        assert "文本 B" in response.text

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    def test_compare_submit_has_radar_chart(self, mock_score, web_client):
        """POST /compare-submit returns SVG radar chart."""
        mock_score.return_value = _make_score_result()

        response = web_client.post(
            "/compare-submit",
            data={"text_a": "First text", "text_b": "Second text"},
        )

        assert response.status_code == 200
        assert "<svg" in response.text
        assert "雷达" in response.text

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    def test_compare_submit_scorer_raises(self, mock_score, web_client):
        """POST /compare-submit returns 500 when scorer raises."""
        mock_score.side_effect = RuntimeError("LLM API error")

        response = web_client.post(
            "/compare-submit",
            data={"text_a": "First text", "text_b": "Second text"},
        )

        assert response.status_code == 500


# ---------------------------------------------------------------------------
# Simple mode tests
# ---------------------------------------------------------------------------


class TestSimpleMode:
    """Tests for simple mode template and UI."""

    def test_base_template_has_simple_mode_toggle(self, web_client):
        """Base template includes simple mode toggle button."""
        response = web_client.get("/dashboard")
        assert "simple-mode-btn" in response.text
        assert "toggleSimpleMode" in response.text

    def test_base_template_has_simple_mode_js(self, web_client):
        """Base template includes simple mode localStorage logic."""
        response = web_client.get("/dashboard")
        assert "simple_mode" in response.text
        assert "localStorage" in response.text

    def test_result_template_has_simple_only_section(self, web_client):
        """Result template includes simple-only view section."""
        with patch("src.web.router.query") as mock_query:
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
                    "summary": "Good content",
                    "model_used": "test",
                    "cost": 0.0,
                    "confidence": 0.9,
                    "scored_at": "2024-01-01T12:00:00",
                    "title": "Test",
                    "source_url": None,
                }
            ]
            response = web_client.get("/result/1")
            assert response.status_code == 200
            assert "simple-only" in response.text
            assert "detail-section" in response.text


# ---------------------------------------------------------------------------
# Pagination and count_records tests
# ---------------------------------------------------------------------------


class TestCountRecords:
    """Tests for count_records() function in db.py."""

    def test_count_records_empty_db(self, tmp_db_path):
        """count_records returns 0 for empty database."""
        init_db(tmp_db_path)
        total = count_records(db_path=tmp_db_path)
        assert total == 0

    def test_count_records_with_data(self, tmp_db_path):
        """count_records returns correct count after inserts."""
        init_db(tmp_db_path)
        # Insert test records
        for i in range(5):
            result = ScoreResult(
                overall_score=50.0 + i * 10,
                dimensions=DimensionScores(
                    originality=50,
                    info_density=50,
                    reasoning_quality=50,
                    readability=50,
                    timeliness=50,
                    ai_generated_prob=10,
                    emotional_manipulation=10,
                    advertorial_prob=10,
                    scam_prob=10,
                ),
                labels=[],
                summary="Test",
                confidence=0.9,
                model_used="test",
                cost=0.0,
            )
            content = Content(
                input_type=InputType.TEXT,
                text=f"test content number {i} unique text",
                title=f"Test {i}",
            )
            content.compute_hash()
            save(result, content, db_path=tmp_db_path)

        total = count_records(db_path=tmp_db_path)
        assert total == 5

    def test_count_records_with_filter(self, tmp_db_path):
        """count_records respects filter conditions."""
        init_db(tmp_db_path)
        for i in range(5):
            result = ScoreResult(
                overall_score=30.0 + i * 15,
                dimensions=DimensionScores(
                    originality=50,
                    info_density=50,
                    reasoning_quality=50,
                    readability=50,
                    timeliness=50,
                    ai_generated_prob=10,
                    emotional_manipulation=10,
                    advertorial_prob=10,
                    scam_prob=10,
                ),
                labels=[],
                summary="Test",
                confidence=0.9,
                model_used="test",
                cost=0.0,
            )
            content = Content(
                input_type=InputType.TEXT,
                text=f"filter test content number {i} unique",
                title=f"Filter Test {i}",
            )
            content.compute_hash()
            save(result, content, db_path=tmp_db_path)

        # Filter for min_score >= 60 (scores: 30, 45, 60, 75, 90) => 3 match
        total = count_records(filters={"min_score": 60}, db_path=tmp_db_path)
        assert total == 3


class TestQueryOffset:
    """Tests for query() with offset parameter."""

    def test_query_with_offset(self, tmp_db_path):
        """query() with offset skips the first N records."""
        init_db(tmp_db_path)
        for i in range(10):
            result = ScoreResult(
                overall_score=50.0 + i,
                dimensions=DimensionScores(
                    originality=50,
                    info_density=50,
                    reasoning_quality=50,
                    readability=50,
                    timeliness=50,
                    ai_generated_prob=10,
                    emotional_manipulation=10,
                    advertorial_prob=10,
                    scam_prob=10,
                ),
                labels=[],
                summary="Test",
                confidence=0.9,
                model_used="test",
                cost=0.0,
            )
            content = Content(
                input_type=InputType.TEXT,
                text=f"offset test content number {i} unique text here",
                title=f"Offset Test {i}",
            )
            content.compute_hash()
            save(result, content, db_path=tmp_db_path)

        # Get first 5
        page1 = query(limit=5, offset=0, db_path=tmp_db_path)
        assert len(page1) == 5

        # Get next 5
        page2 = query(limit=5, offset=5, db_path=tmp_db_path)
        assert len(page2) == 5

        # Results should not overlap
        page1_ids = {r["id"] for r in page1}
        page2_ids = {r["id"] for r in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_query_offset_beyond_results(self, tmp_db_path):
        """query() with offset beyond available results returns empty."""
        init_db(tmp_db_path)
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=10,
                emotional_manipulation=10,
                advertorial_prob=10,
                scam_prob=10,
            ),
            labels=[],
            summary="Test",
            confidence=0.9,
            model_used="test",
            cost=0.0,
        )
        content = Content(
            input_type=InputType.TEXT,
            text="single record unique content",
            title="Single",
        )
        content.compute_hash()
        save(result, content, db_path=tmp_db_path)

        results = query(limit=20, offset=100, db_path=tmp_db_path)
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Performance and nav tests
# ---------------------------------------------------------------------------


class TestPerformancePolish:
    """Tests for performance optimizations in base.html."""

    def test_inline_critical_css(self, web_client):
        """base.html has inline critical CSS in a <style> tag."""
        response = web_client.get("/dashboard")
        assert "<style>" in response.text
        assert "font-family" in response.text

    def test_font_display_swap(self, web_client):
        """Google Fonts URL includes display=swap."""
        response = web_client.get("/dashboard")
        assert "display=swap" in response.text

    def test_stylesheet_preload(self, web_client):
        """base.html has preload link for main stylesheet."""
        response = web_client.get("/dashboard")
        assert 'rel="preload"' in response.text
        assert 'as="style"' in response.text

    def test_compare_nav_link(self, web_client):
        """base.html nav includes compare link."""
        response = web_client.get("/dashboard")
        assert "/compare" in response.text
        assert "对比" in response.text
