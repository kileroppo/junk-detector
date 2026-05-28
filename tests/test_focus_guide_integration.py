"""Integration tests for Focus Guide in web router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models.score import Content, DimensionScores, InputType, ScoreResult


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


def _make_ai_score_result() -> ScoreResult:
    """Create a ScoreResult with high ai_generated_prob (should trigger focus guide)."""
    return ScoreResult(
        overall_score=30.0,
        dimensions=DimensionScores(
            originality=20,
            info_density=25,
            reasoning_quality=30,
            readability=50,
            timeliness=30,
            ai_generated_prob=85,
            emotional_manipulation=15,
            advertorial_prob=20,
            scam_prob=10,
        ),
        labels=["可能AI生成"],
        summary="AI generated content detected",
        confidence=0.9,
        model_used="test",
        cost=0.001,
    )


def _make_high_quality_score_result() -> ScoreResult:
    """Create a ScoreResult with high quality (should NOT trigger focus guide)."""
    return ScoreResult(
        overall_score=85.0,
        dimensions=DimensionScores(
            originality=90,
            info_density=85,
            reasoning_quality=80,
            readability=90,
            timeliness=75,
            ai_generated_prob=10,
            emotional_manipulation=5,
            advertorial_prob=10,
            scam_prob=2,
        ),
        labels=["高质量原创"],
        summary="Excellent original content",
        confidence=0.95,
        model_used="test",
        cost=0.001,
    )


def _make_content(text: str = "test text") -> Content:
    """Create a Content object."""
    return Content(
        input_type=InputType.TEXT,
        text=text,
        title="Test Title",
        source_url=None,
    )


# AI-like text for triggering focus guide
AI_TEXT = """首先，在当今社会，人工智能技术已经成为了一个不可忽视的力量。众所周知，AI技术正在深刻地改变着我们的生活方式和工作模式。

其次，随着科技的发展，越来越多的企业开始将人工智能应用到实际生产中。不言而喻，这种趋势将会持续下去。

再次，我们需要认识到人工智能带来的机遇和挑战。毋庸置疑，AI技术在提高效率的同时也带来了需要思考的问题。

最后，综上所述，人工智能技术的发展是不可逆转的趋势。我们应该积极拥抱这一变化。"""


class TestFocusGuideIntegration:
    """Integration tests for focus guide in score_submit endpoint."""

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_shown_for_ai_content(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """POST /score-submit with AI-scored content shows focus guide in response."""
        mock_extract.return_value = _make_content(text=AI_TEXT)
        mock_score.return_value = _make_ai_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": AI_TEXT},
        )

        assert response.status_code == 200
        html = response.text
        # Focus guide section should be present
        assert "重点关注指南" in html

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_not_shown_for_high_quality(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """POST /score-submit with high-quality content does NOT show focus guide."""
        mock_extract.return_value = _make_content(text="High quality original content")
        mock_score.return_value = _make_high_quality_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": "High quality original content"},
        )

        assert response.status_code == 200
        html = response.text
        # Focus guide section should NOT be present
        assert "重点关注指南" not in html

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_shows_recommendation(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """Focus guide should show a recommendation badge."""
        mock_extract.return_value = _make_content(text=AI_TEXT)
        mock_score.return_value = _make_ai_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": AI_TEXT},
        )

        assert response.status_code == 200
        html = response.text
        # Should contain one of the recommendation labels
        assert any(
            label in html
            for label in ["建议跳过", "建议略读", "建议细读"]
        )

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_shows_ai_patterns(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """Focus guide should show AI pattern detection section."""
        mock_extract.return_value = _make_content(text=AI_TEXT)
        mock_score.return_value = _make_ai_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": AI_TEXT},
        )

        assert response.status_code == 200
        html = response.text
        assert "AI生成特征" in html

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_shows_tldr(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """Focus guide should show TL;DR section."""
        mock_extract.return_value = _make_content(text=AI_TEXT)
        mock_score.return_value = _make_ai_score_result()
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": AI_TEXT},
        )

        assert response.status_code == 200
        html = response.text
        assert "TL;DR" in html

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_with_low_score_content(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """Low overall score (< 50) even with moderate ai_prob triggers focus guide."""
        low_score = ScoreResult(
            overall_score=35.0,
            dimensions=DimensionScores(
                originality=40,
                info_density=30,
                reasoning_quality=35,
                readability=50,
                timeliness=30,
                ai_generated_prob=45,  # Below 50 but overall_score < 50
                emotional_manipulation=20,
                advertorial_prob=30,
                scam_prob=15,
            ),
            labels=[],
            summary="Low quality content",
            confidence=0.8,
            model_used="test",
            cost=0.001,
        )
        mock_extract.return_value = _make_content(text=AI_TEXT)
        mock_score.return_value = low_score
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": AI_TEXT},
        )

        assert response.status_code == 200
        html = response.text
        assert "重点关注指南" in html

    @patch("src.core.scorer.score", new_callable=AsyncMock)
    @patch("src.storage.db.save")
    @patch("src.extractors.text.extract_from_text")
    def test_focus_guide_mid_range_content_gets_guide(
        self, mock_extract, mock_save, mock_score, web_client
    ):
        """Content in middle range (score 55, ai_prob 40) should get a focus guide.

        This tests the fix for the gating mismatch where the router gate was
        too narrow (score < 50 OR ai_prob > 50) and missed borderline content.
        """
        mid_range_score = ScoreResult(
            overall_score=55.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=45,
                reasoning_quality=55,
                readability=60,
                timeliness=50,
                ai_generated_prob=40,
                emotional_manipulation=15,
                advertorial_prob=20,
                scam_prob=10,
            ),
            labels=[],
            summary="Borderline content",
            confidence=0.85,
            model_used="test",
            cost=0.001,
        )
        mock_extract.return_value = _make_content(text=AI_TEXT)
        mock_score.return_value = mid_range_score
        mock_save.return_value = None

        response = web_client.post(
            "/score-submit",
            data={"input_type": "text", "text": AI_TEXT},
        )

        assert response.status_code == 200
        html = response.text
        # With the widened gate (score < 70 OR ai_prob > 30), this mid-range
        # content should now get a focus guide generated
        assert "重点关注指南" in html
