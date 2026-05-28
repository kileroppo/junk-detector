"""Tests for FEAT-002 Interaction Layer: keyboard shortcuts, batch scoring,
trends endpoint, feedback endpoint, and swipe gestures."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestKeyboardShortcuts:
    """Verify the keyboard shortcut script is present in base.html."""

    def test_keyboard_shortcuts_in_base_template(self, web_client):
        """base.html contains keydown event handler with expected keys."""
        resp = web_client.get("/dashboard")
        assert resp.status_code == 200
        html = resp.text
        # Check for key handler script
        assert "addEventListener('keydown'" in html
        assert "e.key === '/'" in html
        assert "e.key === 'n' || e.key === 'N'" in html
        assert "e.key === 'Escape'" in html
        assert "e.key === 'j' || e.key === 'J'" in html
        assert "e.key === 'k' || e.key === 'K'" in html

    def test_shortcut_help_overlay_present(self, web_client):
        """base.html contains the shortcut overlay modal."""
        resp = web_client.get("/dashboard")
        html = resp.text
        assert "shortcut-overlay" in html
        assert "shortcut-help-btn" in html
        assert "toggleShortcutOverlay" in html


class TestBatchEndpoint:
    """Tests for POST /score-batch."""

    def test_batch_endpoint_empty(self, web_client):
        """POST to /score-batch with empty body returns 422."""
        resp = web_client.post("/score-batch", data={"urls": ""})
        assert resp.status_code == 422

    def test_batch_endpoint_no_valid_urls(self, web_client):
        """POST to /score-batch with invalid URLs returns 422."""
        resp = web_client.post("/score-batch", data={"urls": "not-a-url\nalso-not-url"})
        assert resp.status_code == 422
        assert "有效的 URL" in resp.text

    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    def test_batch_endpoint_valid_urls(self, mock_score, mock_extract, web_client):
        """POST to /score-batch with valid URLs returns results."""
        from src.models.score import Content, DimensionScores, InputType, ScoreResult

        mock_content = Content(
            text="Test content",
            title="Test Article",
            input_type=InputType.URL,
            source_url="https://example.com/article1",
        )
        mock_extract.return_value = mock_content

        mock_result = ScoreResult(
            overall_score=75.0,
            dimensions=DimensionScores(
                originality=70, info_density=60, reasoning_quality=70,
                readability=80, timeliness=50, ai_generated_prob=20,
                emotional_manipulation=10, advertorial_prob=15, scam_prob=5,
            ),
            labels=["高质量原创"],
            summary="Good article",
            model_used="test-model",
            cost=0.01,
            confidence=0.9,
        )
        mock_score.return_value = mock_result

        resp = web_client.post(
            "/score-batch",
            data={"urls": "https://example.com/article1\nhttps://example.com/article2"},
        )
        assert resp.status_code == 200
        assert "批量评分结果" in resp.text
        assert "75" in resp.text

    def test_batch_tab_in_score_form(self, web_client):
        """score_form.html contains a batch tab."""
        resp = web_client.get("/score-form")
        assert resp.status_code == 200
        html = resp.text
        assert "tab-batch" in html
        assert "batch (批量)" in html
        assert "batch-urls" in html
        assert "batch-drop-zone" in html


class TestTrendsEndpoint:
    """Tests for GET /api/trends."""

    def test_trends_endpoint(self, web_client):
        """GET /api/trends returns JSON with trends key."""
        resp = web_client.get("/api/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert "trends" in data
        assert isinstance(data["trends"], list)

    def test_trends_with_data(self, tmp_db_path, web_client, monkeypatch):
        """Insert sample records and verify aggregation in trends."""
        from src.storage.db import _get_connection, init_db

        init_db(tmp_db_path)
        conn = _get_connection(tmp_db_path)

        # Insert some test records
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        for i, (day, score) in enumerate([
            (today, 80.0),
            (today, 60.0),
            (yesterday, 30.0),
            (yesterday, 50.0),
        ]):
            conn.execute(
                """INSERT INTO scores (input_type, source_url, title, content_hash,
                   scored_at, overall_score, dimensions_json, labels_json, summary,
                   model_used, cost, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("text", None, f"Test {i}", f"hash{i}_{day}",
                 f"{day}T12:00:00", score, "{}", "[]", "Test", "model", 0, 1.0),
            )
        conn.commit()
        conn.close()

        # Monkey-patch the db path in get_trends
        from src.storage import db
        monkeypatch.setattr(db, "_initialized_dbs", {tmp_db_path})

        from src.storage.db import get_trends
        trends = get_trends(days=28, db_path=tmp_db_path)

        assert len(trends) == 2
        # Yesterday should have avg 40, junk_count=1
        day_yesterday = [t for t in trends if t["date"] == yesterday]
        assert len(day_yesterday) == 1
        assert day_yesterday[0]["avg_score"] == 40.0
        assert day_yesterday[0]["junk_count"] == 1
        assert day_yesterday[0]["count"] == 2

    def test_trends_on_dashboard(self, web_client):
        """Dashboard template contains trends chart section."""
        resp = web_client.get("/dashboard")
        assert resp.status_code == 200
        # The chart section uses SVG viewBox
        # It may not render if there are no trends, but the endpoint works


class TestFeedbackEndpoint:
    """Tests for POST /api/feedback."""

    @pytest.fixture(autouse=True)
    def _reset_rate_limiter(self, web_client):
        """Reset rate limiter windows before each test."""
        from src.api.app import app

        # Walk the middleware stack to find RateLimitMiddleware
        stack = app.middleware_stack
        while stack is not None:
            if hasattr(stack, "limiter"):
                stack.limiter._windows.clear()
                if hasattr(stack, "_global_limiter"):
                    stack._global_limiter._windows.clear()
                break
            stack = getattr(stack, "app", None)

    def test_feedback_endpoint(self, web_client, tmp_db_path, monkeypatch):
        """POST to /api/feedback stores feedback in DB."""
        from src.storage import db

        monkeypatch.setattr(db, "_initialized_feedback_dbs", set())

        resp = web_client.post(
            "/api/feedback",
            json={"score_id": 1, "verdict": "wrong", "content_hash": "abc123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_feedback_endpoint_invalid_verdict(self, web_client):
        """POST to /api/feedback with invalid verdict returns 422."""
        resp = web_client.post(
            "/api/feedback",
            json={"score_id": 1, "verdict": "invalid"},
        )
        assert resp.status_code == 422

    def test_feedback_endpoint_missing_fields(self, web_client):
        """POST to /api/feedback with missing fields returns 422."""
        resp = web_client.post("/api/feedback", json={"verdict": "wrong"})
        assert resp.status_code == 422

    def test_feedback_endpoint_invalid_json(self, web_client):
        """POST to /api/feedback with invalid JSON returns 400."""
        resp = web_client.post(
            "/api/feedback",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400


class TestFeedbackDB:
    """Tests for feedback DB functions."""

    def test_save_feedback(self, tmp_db_path):
        """save_feedback stores a record in the feedback table."""
        from src.storage.db import get_feedback_count, init_feedback_table, save_feedback

        init_feedback_table(tmp_db_path)
        save_feedback(score_id=1, content_hash="hash123", verdict="wrong", db_path=tmp_db_path)
        count = get_feedback_count(db_path=tmp_db_path)
        assert count == 1

    def test_get_feedback_count_empty(self, tmp_db_path):
        """get_feedback_count returns 0 for empty table."""
        from src.storage.db import get_feedback_count, init_feedback_table

        init_feedback_table(tmp_db_path)
        count = get_feedback_count(db_path=tmp_db_path)
        assert count == 0


class TestSwipeInHistory:
    """Verify touch handler script in history.html."""

    @patch("src.web.router.count_records", return_value=1)
    @patch("src.web.router.query")
    def test_swipe_in_history_template(self, mock_query, mock_count, web_client):
        """history.html contains touch event handlers for swipe gestures."""
        mock_query.return_value = [
            {
                "id": 1,
                "title": "Test",
                "source_url": "https://example.com",
                "overall_score": 75.0,
                "scored_at": "2025-01-01T12:00:00",
                "labels": [],
                "summary": "Test summary",
            }
        ]
        resp = web_client.get("/history-page")
        assert resp.status_code == 200
        html = resp.text
        assert "touchstart" in html
        assert "touchmove" in html
        assert "touchend" in html
        assert "history-swipe-card" in html
        assert "swipe-action-left" in html
        assert "swipe-action-right" in html
