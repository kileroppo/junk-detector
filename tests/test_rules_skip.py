"""Tests for smart rules skip logic (should_skip_llm) and scoring stats tracking.

Covers:
- should_skip_llm function with various rule result scenarios
- Scorer integration: verifies LLM is skipped/called based on rules confidence
- Stats tracking: increment_rules_only, increment_llm_count, get_daily_stats
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

from src.core.rules import RuleResult, should_skip_llm
from src.storage.db import (
    get_daily_stats,
    increment_llm_count,
    increment_rules_only,
    init_scoring_stats_table,
)

# ---------------------------------------------------------------------------
# Tests for should_skip_llm
# ---------------------------------------------------------------------------


class TestShouldSkipLlm:
    """Tests for the should_skip_llm function."""

    def test_high_confidence_multi_keyword_returns_true(self):
        """When >= 3 non-combo rules fired with avg confidence >= 0.85, skip LLM."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases", "advertorial_promo"],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
                "advertorial_prob": 80.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
                "advertorial_prob": 0.85,
            },
        )
        should_skip, reason = should_skip_llm(rule_result, "some scammy text")
        assert should_skip is True
        assert reason == "high_confidence_rules"

    def test_high_confidence_with_combo_rules_still_counts_non_combo_only(self):
        """Combo rules are not counted toward the >= 3 non-combo threshold."""
        rule_result = RuleResult(
            matched_rules=[
                "scam_keywords",
                "emotional_anxiety_phrases",
                "combo_engagement_bait",
                "combo_crypto_scam_combo",
            ],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
            },
        )
        # Only 2 non-combo rules, so should NOT skip
        should_skip, reason = should_skip_llm(rule_result, "some text")
        assert should_skip is False
        assert reason == "insufficient_confidence"

    def test_single_keyword_returns_false(self):
        """A single rule hit is not sufficient to skip LLM."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 75.0},
            confidence={"scam_prob": 0.8},
        )
        should_skip, reason = should_skip_llm(rule_result, "text with one scam keyword")
        assert should_skip is False
        assert reason == "insufficient_confidence"

    def test_three_rules_but_low_confidence_returns_false(self):
        """Three rules matched but avg confidence < 0.85 should not skip."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases", "advertorial_promo"],
            dimension_overrides={
                "scam_prob": 75.0,
                "emotional_manipulation": 70.0,
                "advertorial_prob": 60.0,
            },
            confidence={
                "scam_prob": 0.8,
                "emotional_manipulation": 0.75,
                "advertorial_prob": 0.7,
            },
        )
        should_skip, reason = should_skip_llm(rule_result, "text")
        assert should_skip is False
        assert reason == "insufficient_confidence"

    def test_no_keywords_long_text_returns_clean_prose_needs_llm(self):
        """No rules matched + long text (> 1000 chars) returns clean_prose_needs_llm."""
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        long_text = "a" * 1001
        should_skip, reason = should_skip_llm(rule_result, long_text)
        assert should_skip is False
        assert reason == "clean_prose_needs_llm"

    def test_no_keywords_short_text_returns_insufficient_confidence(self):
        """No rules matched + short text returns insufficient_confidence."""
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        short_text = "a" * 500
        should_skip, reason = should_skip_llm(rule_result, short_text)
        assert should_skip is False
        assert reason == "insufficient_confidence"

    def test_combo_only_rules_not_counted(self):
        """If only combo rules fired, non-combo count is 0 -> treated as no keywords."""
        rule_result = RuleResult(
            matched_rules=[
                "combo_engagement_bait",
                "combo_crypto_scam_combo",
                "combo_fomo_urgency",
            ],
            dimension_overrides={
                "advertorial_prob": 80.0,
                "scam_prob": 90.0,
                "emotional_manipulation": 75.0,
            },
            confidence={
                "advertorial_prob": 0.9,
                "scam_prob": 0.95,
                "emotional_manipulation": 0.85,
            },
        )
        long_text = "x" * 1500
        should_skip, reason = should_skip_llm(rule_result, long_text)
        assert should_skip is False
        assert reason == "clean_prose_needs_llm"

    def test_exactly_three_non_combo_rules_at_threshold(self):
        """Exactly 3 non-combo rules with avg confidence exactly 0.85 should skip."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases", "ai_generated_signals"],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 70.0,
                "ai_generated_prob": 65.0,
            },
            confidence={
                "scam_prob": 0.90,
                "emotional_manipulation": 0.85,
                "ai_generated_prob": 0.80,
            },
        )
        # avg = (0.90 + 0.85 + 0.80) / 3 = 0.85
        should_skip, reason = should_skip_llm(rule_result, "text")
        assert should_skip is True
        assert reason == "high_confidence_rules"

    def test_four_non_combo_rules_high_confidence(self):
        """4 non-combo rules with high confidence should skip."""
        rule_result = RuleResult(
            matched_rules=[
                "scam_keywords",
                "emotional_anxiety_phrases",
                "advertorial_promo",
                "ai_generated_signals",
            ],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
                "advertorial_prob": 80.0,
                "ai_generated_prob": 65.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
                "advertorial_prob": 0.85,
                "ai_generated_prob": 0.90,
            },
        )
        should_skip, reason = should_skip_llm(rule_result, "some text")
        assert should_skip is True
        assert reason == "high_confidence_rules"


# ---------------------------------------------------------------------------
# Tests for scorer integration
# ---------------------------------------------------------------------------


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


class TestScorerIntegrationWithSkip:
    """Tests verifying scorer correctly skips or calls LLM based on rules skip logic."""

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_llm_skipped_when_high_confidence_multi_rule(self, mock_filter, mock_acompletion):
        """When rules produce high confidence across >= 3 categories, LLM is NOT called."""
        from src.core.content_filter import FilterResult
        from src.core.scorer import score

        mock_filter.return_value = FilterResult(passed=True)

        # Mock apply_rules to return high confidence across 3 dimensions
        mock_rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases", "advertorial_promo"],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
                "advertorial_prob": 80.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
                "advertorial_prob": 0.85,
            },
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            with patch("src.storage.db.increment_rules_only") as _mock_stats:
                result = await score("日入过万 震惊 必看 推荐码 优惠券 限时免费")

        assert result.model_used == "rules_skip"
        assert result.cost == 0.0
        mock_acompletion.assert_not_called()
        # Verify dimensions are set correctly
        assert result.dimensions.scam_prob == 95.0
        assert result.dimensions.emotional_manipulation == 85.0
        assert result.dimensions.advertorial_prob == 80.0
        # Positive dims should have defaults (50)
        assert result.dimensions.originality == 50.0
        assert result.dimensions.info_density == 50.0
        assert result.dimensions.reasoning_quality == 50.0
        assert result.dimensions.readability == 50.0
        assert result.dimensions.timeliness == 50.0

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_llm_called_when_clean_text(self, mock_filter, mock_acompletion):
        """Clean text with no rule hits should still call LLM."""
        from src.core.content_filter import FilterResult
        from src.core.scorer import score

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(_make_llm_response_content())

        # This is clean text that won't trigger rules
        clean_text = (
            "这是一篇关于人工智能技术发展的客观分析文章，深入探讨了机器学习在医疗领域的应用前景。"
        )

        with patch("src.storage.db.increment_llm_count"):
            result = await score(clean_text)

        assert mock_acompletion.called
        assert result.model_used != "rules_skip"
        assert result.model_used != "rules_only"

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_rules_skip_produces_valid_labels(self, mock_filter, mock_acompletion):
        """When rules skip is triggered, labels are still generated from thresholds."""
        from src.core.content_filter import FilterResult
        from src.core.scorer import score

        mock_filter.return_value = FilterResult(passed=True)

        mock_rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases", "advertorial_promo"],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
                "advertorial_prob": 80.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
                "advertorial_prob": 0.85,
            },
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            with patch("src.storage.db.increment_rules_only"):
                result = await score("scammy text")

        # Labels should be generated for high scores
        assert "疑似骗局" in result.labels  # scam_prob 95 > threshold 60
        assert "情绪操纵" in result.labels  # emotional_manipulation 85 > threshold 65
        assert "疑似软文" in result.labels  # advertorial_prob 80 > threshold 70

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_rules_skip_overall_score_is_valid(self, mock_filter, mock_acompletion):
        """When rules skip is triggered, overall_score is properly calculated."""
        from src.core.content_filter import FilterResult
        from src.core.scorer import score

        mock_filter.return_value = FilterResult(passed=True)

        mock_rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases", "advertorial_promo"],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
                "advertorial_prob": 80.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
                "advertorial_prob": 0.85,
            },
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            with patch("src.storage.db.increment_rules_only"):
                result = await score("high confidence scam text")

        assert 0 <= result.overall_score <= 100
        # With high negative dims, overall should be low
        assert result.overall_score < 50

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_two_rules_does_not_trigger_skip(self, mock_filter, mock_acompletion):
        """Only 2 non-combo rules should NOT trigger skip, LLM should be called."""
        from src.core.content_filter import FilterResult
        from src.core.scorer import score

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(_make_llm_response_content())

        mock_rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases"],
            dimension_overrides={
                "scam_prob": 95.0,
                "emotional_manipulation": 85.0,
            },
            confidence={
                "scam_prob": 0.95,
                "emotional_manipulation": 0.90,
            },
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            with patch("src.storage.db.increment_llm_count"):
                result = await score("partial scam text")

        assert mock_acompletion.called
        assert result.model_used != "rules_skip"


# ---------------------------------------------------------------------------
# Tests for scoring stats tracking
# ---------------------------------------------------------------------------


class TestScoringStats:
    """Tests for scoring stats database tracking."""

    def test_init_scoring_stats_table(self, tmp_path):
        """Initializing the scoring stats table creates it without error."""
        db_path = str(tmp_path / "test_stats.db")
        init_scoring_stats_table(db_path)
        # Calling again should be idempotent
        init_scoring_stats_table(db_path)
        stats = get_daily_stats(db_path)
        assert stats == {"rules_only_count": 0, "llm_count": 0}

    def test_increment_rules_only(self, tmp_path):
        """increment_rules_only increases the counter for today."""
        db_path = str(tmp_path / "test_stats.db")
        increment_rules_only(db_path)
        increment_rules_only(db_path)
        increment_rules_only(db_path)
        stats = get_daily_stats(db_path)
        assert stats["rules_only_count"] == 3
        assert stats["llm_count"] == 0

    def test_increment_llm_count(self, tmp_path):
        """increment_llm_count increases the counter for today."""
        db_path = str(tmp_path / "test_stats.db")
        increment_llm_count(db_path)
        increment_llm_count(db_path)
        stats = get_daily_stats(db_path)
        assert stats["rules_only_count"] == 0
        assert stats["llm_count"] == 2

    def test_both_counters_independent(self, tmp_path):
        """Both counters track independently in the same row."""
        db_path = str(tmp_path / "test_stats.db")
        increment_rules_only(db_path)
        increment_rules_only(db_path)
        increment_llm_count(db_path)
        increment_llm_count(db_path)
        increment_llm_count(db_path)
        stats = get_daily_stats(db_path)
        assert stats["rules_only_count"] == 2
        assert stats["llm_count"] == 3

    def test_get_daily_stats_nonexistent_date(self, tmp_path):
        """Querying a date with no data returns zeroes."""
        db_path = str(tmp_path / "test_stats.db")
        init_scoring_stats_table(db_path)
        stats = get_daily_stats(db_path, target_date="2020-01-01")
        assert stats == {"rules_only_count": 0, "llm_count": 0}

    def test_get_daily_stats_specific_date(self, tmp_path):
        """Stats are recorded under today's date and can be queried by date."""
        db_path = str(tmp_path / "test_stats.db")
        increment_rules_only(db_path)
        today = date.today().isoformat()
        stats = get_daily_stats(db_path, target_date=today)
        assert stats["rules_only_count"] == 1

    def test_multiple_calls_are_atomic(self, tmp_path):
        """Multiple increments all succeed and accumulate correctly."""
        db_path = str(tmp_path / "test_stats.db")
        for _ in range(10):
            increment_rules_only(db_path)
        for _ in range(5):
            increment_llm_count(db_path)
        stats = get_daily_stats(db_path)
        assert stats["rules_only_count"] == 10
        assert stats["llm_count"] == 5
