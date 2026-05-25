"""Tests for the main scoring orchestrator (src.core.scorer).

Verifies the score() function coordinates rules, content filter,
and LLM judge correctly. All LLM calls are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scorer import _calculate_overall, _generate_labels, score
from src.models.score import DimensionScores, ScoreResult, ScoringConfig


def _make_llm_response_content(dimensions: dict | None = None) -> str:
    """Build a JSON string like what litellm returns from the LLM."""
    data = {
        "originality": 75,
        "info_density": 60,
        "reasoning_quality": 70,
        "readability": 80,
        "timeliness": 50,
        "ai_generated_prob": 20,
        "emotional_manipulation": 10,
        "advertorial_prob": 15,
        "scam_prob": 5,
        "summary": "Test content evaluation",
        "confidence": 0.85,
        "labels": [],
    }
    if dimensions:
        data.update(dimensions)
    return json.dumps(data)


def _make_mock_litellm_response(content: str, cost: float = 0.001):
    """Create a mock object matching litellm.acompletion() return shape."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response._hidden_params = {"response_cost": cost}
    return mock_response


class TestScoreOrchestration:
    """Tests verifying the scoring orchestrator behavior."""

    @patch("src.core.scorer.judge")
    @patch("src.core.content_filter.check_content")
    async def test_content_filter_rejection_returns_score_zero(
        self, mock_filter, mock_judge
    ):
        """When content filter rejects content, score is 0 and LLM is not called."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(
            passed=False,
            violation_type="赌博",
            violation_details="detected gambling content",
            matched_patterns=["网上赌场", "在线博彩"],
        )
        result = await score("网上赌场在线博彩赌球")
        assert result.overall_score == 0.0
        assert result.model_used == "content_filter"
        mock_judge.assert_not_called()

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_llm_called_when_rules_dont_cover_all_dimensions(
        self, mock_filter, mock_acompletion
    ):
        """LLM judge is invoked when rules cannot cover all 9 dimensions."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        result = await score("A normal article about technology trends.")
        assert mock_acompletion.called
        assert result.model_used != "rules_only"

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_fallback_model_triggered_on_low_confidence(
        self, mock_filter, mock_acompletion
    ):
        """When primary model returns low confidence, fallback model is called."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # Primary model returns low confidence, fallback returns high
        low_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.3}), cost=0.001
        )
        high_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.9}), cost=0.002
        )
        mock_acompletion.side_effect = [low_conf_response, high_conf_response]

        config = ScoringConfig(
            primary_model="test/primary",
            fallback_model="test/fallback",
            confidence_threshold=0.7,
        )
        result = await score("Some text to analyze", config=config)
        # Should have been called twice (primary + fallback)
        assert mock_acompletion.call_count == 2

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_cost_accumulation_after_fallback(
        self, mock_filter, mock_acompletion
    ):
        """Total cost includes both primary and fallback model calls."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        primary_cost = 0.005
        fallback_cost = 0.010
        low_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.3}), cost=primary_cost
        )
        high_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.9}), cost=fallback_cost
        )
        mock_acompletion.side_effect = [low_conf_response, high_conf_response]

        config = ScoringConfig(
            primary_model="test/primary",
            fallback_model="test/fallback",
            confidence_threshold=0.7,
        )
        result = await score("Cost test content", config=config)
        assert result.cost == pytest.approx(primary_cost + fallback_cost, abs=0.001)

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_rules_only_path_skips_llm(self, mock_filter, mock_acompletion):
        """When rules cover all 9 dimensions with high confidence, LLM is skipped."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # Patch apply_rules to cover ALL dimensions
        all_dims = [
            "originality", "info_density", "reasoning_quality", "readability",
            "timeliness", "ai_generated_prob", "emotional_manipulation",
            "advertorial_prob", "scam_prob",
        ]
        from src.core.rules import RuleResult

        mock_rule_result = RuleResult(
            matched_rules=["test_rule"],
            dimension_overrides={dim: 50.0 for dim in all_dims},
            confidence={dim: 0.95 for dim in all_dims},
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            result = await score("Any text")

        assert result.model_used == "rules_only"
        assert result.cost == 0.0
        mock_acompletion.assert_not_called()

    def test_calculate_overall_with_default_weights(self):
        """Overall score calculation produces a value in [0, 100]."""
        dimensions = DimensionScores(
            originality=80,
            info_density=70,
            reasoning_quality=75,
            readability=85,
            timeliness=60,
            ai_generated_prob=20,
            emotional_manipulation=10,
            advertorial_prob=15,
            scam_prob=5,
        )
        config = ScoringConfig()
        overall = _calculate_overall(dimensions, config)
        assert 0 <= overall <= 100

    def test_generate_labels_from_high_scores(self):
        """Labels are generated when dimension scores exceed thresholds."""
        dimensions = DimensionScores(
            originality=85,
            info_density=85,
            reasoning_quality=75,
            readability=80,
            timeliness=50,
            ai_generated_prob=80,
            emotional_manipulation=70,
            advertorial_prob=75,
            scam_prob=65,
        )
        config = ScoringConfig()
        labels = _generate_labels(dimensions, config)
        assert "高质量原创" in labels
        assert "信息密度高" in labels
        assert "可能AI生成" in labels
        assert "情绪操纵" in labels
        assert "疑似软文" in labels
        assert "疑似骗局" in labels
