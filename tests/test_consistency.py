"""Tests for the scoring consistency mode (score_consistent)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.scorer import score_consistent
from src.models.score import FastScoreResult, ScoringConfig


def _make_fast_result(
    quick_verdict: float = 70.0,
    scam_prob: float = 10.0,
    advertorial_prob: float = 15.0,
    emotional_manipulation: float = 20.0,
    originality: float = 80.0,
) -> FastScoreResult:
    """Helper to create a FastScoreResult with configurable values."""
    return FastScoreResult(
        quick_verdict=quick_verdict,
        scam_prob=scam_prob,
        advertorial_prob=advertorial_prob,
        emotional_manipulation=emotional_manipulation,
        originality=originality,
        summary="Test result",
        confidence=0.85,
        model_used="test-model",
    )


class TestConsistentScoringRulesOnly:
    """Test that consistent scoring with rules-only returns same result as single run."""

    @pytest.mark.asyncio
    async def test_rules_only_returns_deterministic(self):
        """When rules can determine the result, consistent mode runs once."""
        # Use a known scam text that rules will catch with high confidence
        scam_text = "免费领取 加微信 转账即可 暴富机会 点击链接领取百万现金"

        result = await score_consistent(scam_text, n_runs=3)

        # Rules should handle this deterministically
        assert result.model_used == "rules_only"
        assert "deterministic" in result.summary or "规则引擎" in result.summary

    @pytest.mark.asyncio
    async def test_rules_only_same_as_single_run(self):
        """Rules-only consistent result matches a single fast_scorer run."""
        from src.core.fast_scorer import score_fast

        scam_text = "免费领取 加微信 转账即可 暴富机会 点击链接领取百万现金"

        single_result = await score_fast(scam_text)
        consistent_result = await score_consistent(scam_text, n_runs=5)

        # Both should be rules_only and have same numeric values
        assert single_result.model_used == "rules_only"
        assert consistent_result.model_used == "rules_only"
        assert single_result.quick_verdict == consistent_result.quick_verdict
        assert single_result.scam_prob == consistent_result.scam_prob


class TestConsistentScoringMedian:
    """Test median calculation logic with mocked score_fast."""

    @pytest.mark.asyncio
    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.core.fast_scorer._rules_only_fast_result", return_value=None)
    @patch("src.core.rules.apply_rules")
    async def test_median_of_three_runs(self, mock_apply_rules, mock_rules_fast, mock_score_fast):
        """Median is correctly computed from 3 different LLM results."""
        from src.core.rules import RuleResult

        # Make rules return nothing so LLM path is taken
        mock_apply_rules.return_value = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )

        # Return 3 different results
        mock_score_fast.side_effect = [
            _make_fast_result(quick_verdict=60.0, scam_prob=30.0, originality=70.0),
            _make_fast_result(quick_verdict=80.0, scam_prob=10.0, originality=90.0),
            _make_fast_result(quick_verdict=70.0, scam_prob=20.0, originality=80.0),
        ]

        config = ScoringConfig()
        result = await score_consistent("test content", n_runs=3, config=config)

        # Median of [60, 80, 70] = 70
        assert result.quick_verdict == 70.0
        # Median of [30, 10, 20] = 20
        assert result.scam_prob == 20.0
        # Median of [70, 90, 80] = 80
        assert result.originality == 80.0
        assert "consistent mode (3 runs)" in result.summary

    @pytest.mark.asyncio
    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.core.fast_scorer._rules_only_fast_result", return_value=None)
    @patch("src.core.rules.apply_rules")
    async def test_median_of_five_runs(self, mock_apply_rules, mock_rules_fast, mock_score_fast):
        """Median is correctly computed from 5 different LLM results."""
        from src.core.rules import RuleResult

        mock_apply_rules.return_value = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )

        mock_score_fast.side_effect = [
            _make_fast_result(quick_verdict=50.0),
            _make_fast_result(quick_verdict=90.0),
            _make_fast_result(quick_verdict=60.0),
            _make_fast_result(quick_verdict=80.0),
            _make_fast_result(quick_verdict=70.0),
        ]

        config = ScoringConfig()
        result = await score_consistent("test content", n_runs=5, config=config)

        # Median of [50, 90, 60, 80, 70] = 70
        assert result.quick_verdict == 70.0
        assert "consistent mode (5 runs)" in result.summary

    @pytest.mark.asyncio
    @patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock)
    @patch("src.core.fast_scorer._rules_only_fast_result", return_value=None)
    @patch("src.core.rules.apply_rules")
    async def test_consistent_uses_correct_n_runs(self, mock_apply_rules, mock_rules_fast, mock_score_fast):
        """score_fast is called exactly n_runs times."""
        from src.core.rules import RuleResult

        mock_apply_rules.return_value = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )

        mock_score_fast.return_value = _make_fast_result()

        config = ScoringConfig()
        await score_consistent("test content", n_runs=4, config=config)

        assert mock_score_fast.call_count == 4
