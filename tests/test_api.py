"""Tests for the FastAPI application (src.api.app).

Verifies API endpoints return correct responses with mocked scoring logic.
All LLM and storage calls are mocked to avoid external dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.score import DimensionScores, ScoreResult


@pytest.fixture
def client(set_api_key):
    """Create a TestClient with mocked API key env var for lifespan."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200(self, client):
        """Health check endpoint returns 200 with status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["name"] == "\u9274\u771f"
        assert data["version"] == "0.2.0"
        assert "uptime_seconds" in data
        assert "total_scores" in data
        assert "rules_loaded" in data

    @patch("litellm.acompletion", new_callable=AsyncMock)
    def test_deep_health_check_does_not_leak_errors(self, mock_acompletion, client):
        """Deep health check returns generic message, not exception details."""
        mock_acompletion.side_effect = Exception(
            "Invalid API key: sk-secret-key-here, base_url: https://internal.api.com"
        )
        response = client.get("/health?deep=true")
        assert response.status_code == 200
        data = response.json()
        assert data["llm_status"] == "unreachable"
        assert "error" not in data
        assert "sk-secret" not in json.dumps(data)


class TestScoreEndpoint:
    """Tests for POST /score."""

    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_score_with_text_returns_result(self, mock_score, mock_save, client):
        """Scoring text content returns a valid ScoreResult."""
        mock_result = ScoreResult(
            overall_score=72.5,
            dimensions=DimensionScores(
                originality=75,
                info_density=60,
                reasoning_quality=70,
                readability=80,
                timeliness=50,
                ai_generated_prob=20,
                emotional_manipulation=10,
                advertorial_prob=15,
                scam_prob=5,
            ),
            labels=["高质量原创"],
            summary="Good content",
            confidence=0.85,
            model_used="test-model",
            cost=0.001,
            scored_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_score.return_value = mock_result
        mock_save.return_value = None

        response = client.post("/score", json={"text": "A good article about AI."})
        assert response.status_code == 200
        data = response.json()
        assert data["overall_score"] == 72.5
        assert "dimensions" in data

    def test_score_with_empty_body_returns_422(self, client):
        """Empty request body returns 422 validation error."""
        response = client.post("/score", json={})
        assert response.status_code == 422

    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_score_with_url_calls_extract(self, mock_score, mock_save, client):
        """Providing a URL triggers URL extraction."""
        mock_result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=50,
                emotional_manipulation=50,
                advertorial_prob=50,
                scam_prob=50,
            ),
            labels=[],
            summary="OK",
            confidence=0.8,
            model_used="test-model",
            cost=0.0,
            scored_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_score.return_value = mock_result
        mock_save.return_value = None

        with patch("src.api.app.extract_from_url", new_callable=AsyncMock) as mock_extract:
            from src.models.score import Content, InputType

            mock_extract.return_value = Content(
                input_type=InputType.URL,
                text="Extracted content",
                source_url="https://example.com",
                title="Test",
                content_hash="abc123",
            )
            response = client.post("/score", json={"url": "https://example.com"})
            assert response.status_code == 200
            mock_extract.assert_called_once()


class TestHistoryEndpoint:
    """Tests for GET /history."""

    @patch("src.api.app.query")
    def test_history_returns_list(self, mock_query, client):
        """History endpoint returns a list of results."""
        mock_query.return_value = [{"overall_score": 72.5, "title": "Test Article"}]
        response = client.get("/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @patch("src.api.app.query")
    def test_history_with_filters(self, mock_query, client):
        """History endpoint passes filters to query function."""
        mock_query.return_value = []
        response = client.get("/history?limit=5&min_score=60")
        assert response.status_code == 200
        mock_query.assert_called_once()


class TestDedupBehavior:
    """Tests verifying that the dedup layer does not block scoring."""

    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_second_request_still_scores(self, mock_score, mock_save, client):
        """Even if dedup says 'recently scored', the endpoint still scores content.

        The scorer's own 7-day cache handles actual deduplication.
        """
        mock_result = ScoreResult(
            overall_score=60.0,
            dimensions=DimensionScores(
                originality=60,
                info_density=55,
                reasoning_quality=65,
                readability=70,
                timeliness=50,
                ai_generated_prob=25,
                emotional_manipulation=15,
                advertorial_prob=10,
                scam_prob=5,
            ),
            labels=[],
            summary="Test",
            confidence=0.8,
            model_used="test-model",
            cost=0.001,
            scored_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_score.return_value = mock_result
        mock_save.return_value = None

        # First request
        response1 = client.post("/score", json={"text": "Duplicate content test"})
        assert response1.status_code == 200

        # Second request with same content - should still score (not block)
        response2 = client.post("/score", json={"text": "Duplicate content test"})
        assert response2.status_code == 200
        assert mock_score.call_count == 2


class TestDemoEndpoint:
    """Tests for GET /demo."""

    def test_demo_default_sample(self, client):
        """Demo endpoint returns scoring result for default sample text."""
        response = client.get("/demo")
        assert response.status_code == 200
        data = response.json()
        assert "overall_score" in data
        assert "verdict" in data
        assert "explanation" in data
        assert data["is_custom_text"] is False

    def test_demo_custom_text(self, client):
        """Demo endpoint scores custom text when text parameter is provided."""
        response = client.get("/demo?text=这是一篇普通的技术分享文章")
        assert response.status_code == 200
        data = response.json()
        assert "overall_score" in data
        assert "verdict" in data
        assert data["is_custom_text"] is True
        assert data["text_scored"] == "这是一篇普通的技术分享文章"

    def test_demo_custom_junk_text(self, client):
        """Demo endpoint correctly scores obvious junk text."""
        response = client.get("/demo?text=日入过万 加微信 财富自由 限时免费")
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "junk"
        assert data["is_custom_text"] is True


class TestStartupValidation:
    """Tests for the lifespan startup validation."""

    def test_startup_fails_without_api_key(self, monkeypatch):
        """App startup raises RuntimeError when no LLM API key is configured."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from src.api.app import app

        with pytest.raises(RuntimeError, match="No LLM API key configured"):
            with TestClient(app):
                pass


class TestNotificationDispatch:
    """Tests for notification dispatch after scoring."""

    @patch("src.api.app.dispatcher.notify_score_completed", new_callable=AsyncMock)
    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_score_triggers_notification(
        self, mock_score, mock_save, mock_notify, client
    ):
        """Anonymous scoring does NOT trigger notify_score_completed (no broadcast)."""
        mock_result = ScoreResult(
            overall_score=65.0,
            dimensions=DimensionScores(
                originality=70,
                info_density=60,
                reasoning_quality=65,
                readability=70,
                timeliness=50,
                ai_generated_prob=20,
                emotional_manipulation=10,
                advertorial_prob=15,
                scam_prob=5,
            ),
            labels=["高质量原创"],
            summary="Decent content",
            confidence=0.85,
            model_used="test-model",
            cost=0.001,
            scored_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_score.return_value = mock_result
        mock_save.return_value = None

        response = client.post("/score", json={"text": "Test article for notifications."})
        assert response.status_code == 200
        # Anonymous scoring should NOT broadcast to all clients
        mock_notify.assert_not_called()

    @patch("src.api.websocket.manager.send_to_user", new_callable=AsyncMock)
    @patch("src.api.app.dispatcher.notify_score_completed", new_callable=AsyncMock)
    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_authenticated_score_uses_send_to_user(
        self, mock_score, mock_save, mock_notify, mock_send_to_user, set_api_key
    ):
        """Authenticated scoring uses send_to_user instead of broadcast."""
        mock_result = ScoreResult(
            overall_score=65.0,
            dimensions=DimensionScores(
                originality=70,
                info_density=60,
                reasoning_quality=65,
                readability=70,
                timeliness=50,
                ai_generated_prob=20,
                emotional_manipulation=10,
                advertorial_prob=15,
                scam_prob=5,
            ),
            labels=[],
            summary="Decent content",
            confidence=0.85,
            model_used="test-model",
            cost=0.001,
            scored_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_score.return_value = mock_result
        mock_save.return_value = None

        from src.auth.dependencies import get_optional_user
        from src.auth.models import User

        mock_user = User(
            id=3, username="notifyuser", api_key="test-key", created_at=datetime(2024, 1, 1)
        )

        from src.api.app import app

        app.dependency_overrides[get_optional_user] = lambda: mock_user
        try:
            with TestClient(app) as c:
                response = c.post("/score", json={"text": "Test scoped notification."})
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

        assert response.status_code == 200
        # Authenticated users get scoped delivery via send_to_user
        mock_send_to_user.assert_called_once()
        call_args = mock_send_to_user.call_args
        assert call_args[0][0] == 3  # user_id
        assert call_args[0][1] == "score_completed"  # event
        # Broadcast should NOT have been called
        mock_notify.assert_not_called()


class TestMultiTenantIsolation:
    """Tests for multi-tenant data isolation via user_id."""

    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_authenticated_score_passes_user_id(self, mock_score, mock_save, set_api_key):
        """Authenticated user's score is saved with their user_id."""
        mock_result = ScoreResult(
            overall_score=70.0,
            dimensions=DimensionScores(
                originality=70,
                info_density=70,
                reasoning_quality=70,
                readability=70,
                timeliness=70,
                ai_generated_prob=30,
                emotional_manipulation=10,
                advertorial_prob=10,
                scam_prob=5,
            ),
            labels=[],
            summary="Test",
            confidence=0.9,
            model_used="test-model",
            cost=0.0,
            scored_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_score.return_value = mock_result
        mock_save.return_value = None

        from src.auth.dependencies import get_optional_user
        from src.auth.models import User

        mock_user = User(
            id=7, username="testuser", api_key="test-key", created_at=datetime(2024, 1, 1)
        )

        from src.api.app import app

        app.dependency_overrides[get_optional_user] = lambda: mock_user
        try:
            with TestClient(app) as c:
                response = c.post("/score", json={"text": "Test content for user 7"})
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

        assert response.status_code == 200
        mock_save.assert_called_once()
        _, kwargs = mock_save.call_args
        assert kwargs.get("user_id") == 7

    @patch("src.api.app.query")
    def test_authenticated_history_filters_by_user_id(self, mock_query, set_api_key):
        """Authenticated user's history request filters by their user_id."""
        mock_query.return_value = []

        from src.auth.dependencies import get_optional_user
        from src.auth.models import User

        mock_user = User(
            id=5, username="histuser", api_key="test-key", created_at=datetime(2024, 1, 1)
        )

        from src.api.app import app

        app.dependency_overrides[get_optional_user] = lambda: mock_user
        try:
            with TestClient(app) as c:
                response = c.get("/history")
        finally:
            app.dependency_overrides.pop(get_optional_user, None)

        assert response.status_code == 200
        mock_query.assert_called_once()
        _, kwargs = mock_query.call_args
        assert kwargs.get("user_id") == 5
