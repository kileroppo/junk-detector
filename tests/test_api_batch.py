"""Tests for POST /score/batch endpoint."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.score import DimensionScores, ScoreResult


@pytest.fixture
def client(set_api_key):
    """Create TestClient with API key set."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


def _mock_score_result(score_val: float = 70.0) -> ScoreResult:
    return ScoreResult(
        overall_score=score_val,
        dimensions=DimensionScores(
            originality=70,
            info_density=65,
            reasoning_quality=70,
            readability=75,
            timeliness=60,
            ai_generated_prob=15,
            emotional_manipulation=10,
            advertorial_prob=10,
            scam_prob=5,
        ),
        labels=[],
        summary="Test result",
        confidence=0.85,
        model_used="test-model",
        cost=0.001,
        scored_at=datetime(2024, 1, 1, 12, 0, 0),
    )


class TestBatchScoreEndpoint:
    """Tests for POST /score/batch."""

    @patch("src.api.app.dispatcher.notify_score_completed", new_callable=AsyncMock)
    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_batch_scores_multiple_items(self, mock_score, mock_save, mock_notify, client):
        """Batch endpoint scores all items and returns results."""
        mock_score.return_value = _mock_score_result()
        mock_save.return_value = None

        response = client.post(
            "/score/batch",
            json={
                "items": [
                    {"text": "First article"},
                    {"text": "Second article"},
                    {"text": "Third article"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["errors"] == 0
        assert len(data["results"]) == 3
        assert mock_score.call_count == 3

    @patch("src.api.app.dispatcher.notify_score_completed", new_callable=AsyncMock)
    @patch("src.api.app.save")
    @patch("src.api.app.score")
    @patch("src.api.app.extract_from_url", new_callable=AsyncMock)
    def test_batch_handles_item_errors(
        self, mock_extract, mock_score, mock_save, mock_notify, client
    ):
        """Batch endpoint handles individual item failures gracefully."""
        from src.models.score import Content, InputType

        mock_extract.return_value = Content(
            text="Extracted text", input_type=InputType.URL, source_url="https://bad-url.example.com"
        )
        mock_score.side_effect = [_mock_score_result(), Exception("Network error")]
        mock_save.return_value = None

        response = client.post(
            "/score/batch",
            json={
                "items": [
                    {"text": "Good article"},
                    {"url": "https://bad-url.example.com"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["errors"] == 1

    @patch("src.api.app.dispatcher.notify_score_completed", new_callable=AsyncMock)
    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_batch_notifies_per_item(self, mock_score, mock_save, mock_notify, client):
        """Anonymous batch scoring does NOT trigger WebSocket notifications."""
        mock_score.return_value = _mock_score_result()
        mock_save.return_value = None

        response = client.post(
            "/score/batch",
            json={
                "items": [
                    {"text": "Article one"},
                    {"text": "Article two"},
                ]
            },
        )
        assert response.status_code == 200
        # Anonymous scoring should NOT broadcast to all clients
        mock_notify.assert_not_called()

    def test_batch_empty_items_rejected(self, client):
        """Empty items list returns 422."""
        response = client.post("/score/batch", json={"items": []})
        assert response.status_code == 422

    @patch("src.api.app.dispatcher.notify_score_completed", new_callable=AsyncMock)
    @patch("src.api.app.save")
    @patch("src.api.app.score")
    def test_batch_item_without_text_or_url_returns_error(
        self, mock_score, mock_save, mock_notify, client
    ):
        """Items without text or url return error in results."""
        mock_score.return_value = _mock_score_result()
        mock_save.return_value = None

        response = client.post(
            "/score/batch",
            json={
                "items": [
                    {"text": "Good"},
                    {},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["errors"] == 1
