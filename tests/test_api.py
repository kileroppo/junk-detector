"""Tests for the FastAPI application (src.api.app).

Verifies API endpoints return correct responses with mocked scoring logic.
All LLM and storage calls are mocked to avoid external dependencies.
"""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert response.json() == {"status": "ok"}


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
                originality=50, info_density=50, reasoning_quality=50,
                readability=50, timeliness=50, ai_generated_prob=50,
                emotional_manipulation=50, advertorial_prob=50, scam_prob=50,
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
        mock_query.return_value = [
            {"overall_score": 72.5, "title": "Test Article"}
        ]
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
