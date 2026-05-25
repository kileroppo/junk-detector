"""Tests for the deterministic rules engine (src.core.rules).

Verifies that keyword/regex rules correctly identify content quality signals
and produce appropriate dimension overrides with confidence levels.
"""
from __future__ import annotations

import pytest

from src.core.rules import RuleResult, apply_rules


class TestApplyRulesParametrized:
    """Parametrized tests for apply_rules() covering all rule categories."""

    @pytest.mark.parametrize(
        "text,expected_dimension,min_score,description",
        [
            # Scam rules - 3+ keywords triggers high scam_prob
            (
                "日入过万！躺赚财富自由！限时免费",
                "scam_prob",
                95,
                "3+ scam keywords triggers scam_prob >= 95",
            ),
            # Scam rules - single keyword triggers moderate scam_prob
            (
                "这个项目可以实现日入过万，但需要努力工作",
                "scam_prob",
                75,
                "single scam keyword triggers scam_prob >= 75",
            ),
            # Scam rules - two keywords also triggers >= 75
            (
                "财富自由之路需要你加微信了解更多",
                "scam_prob",
                75,
                "2 scam keywords triggers scam_prob >= 75",
            ),
            # Emotional manipulation - excessive punctuation + anxiety
            (
                "震惊！！！！！！这件事你必须知道！！！再不看就晚了！！！",
                "emotional_manipulation",
                85,
                "anxiety phrases + excessive punctuation triggers >= 85",
            ),
            # Emotional manipulation - excessive punctuation alone
            (
                "太好了！！！！！！这真是太棒了！！！！！！不可思议！！！！！！",
                "emotional_manipulation",
                70,
                "excessive punctuation alone triggers >= 70",
            ),
            # Advertorial - promo keywords + links
            (
                "使用我的推荐码注册 https://a.com https://b.com https://c.com 享受优惠",
                "advertorial_prob",
                80,
                "promo keyword + 3+ links triggers advertorial >= 80",
            ),
            # Advertorial - 2+ promo keywords
            (
                "输入优惠券码获得折扣码，立即省钱",
                "advertorial_prob",
                80,
                "2+ promo keywords triggers advertorial >= 80",
            ),
            # Advertorial - single promo keyword
            (
                "这里有个推荐码可以用来注册",
                "advertorial_prob",
                60,
                "single promo keyword triggers advertorial >= 60",
            ),
            # AI-generated signals - hedging phrases
            (
                "需要注意的是，值得一提的是，总的来说这很重要。需要注意的是这很关键。",
                "ai_generated_prob",
                65,
                "3+ AI hedging phrases triggers ai_generated >= 65",
            ),
            # Scam rules - many keywords for very high confidence
            (
                "日入过万躺赚财富自由限时免费私聊领取月入百万零成本",
                "scam_prob",
                95,
                "many scam keywords (7+) still triggers scam_prob >= 95",
            ),
        ],
        ids=[
            "scam_3_keywords",
            "scam_1_keyword",
            "scam_2_keywords",
            "emotional_punctuation_anxiety",
            "emotional_punctuation_only",
            "advertorial_keywords_links",
            "advertorial_2_keywords",
            "advertorial_1_keyword",
            "ai_hedging_phrases",
            "scam_many_keywords",
        ],
    )
    def test_rule_fires_with_expected_score(
        self, text, expected_dimension, min_score, description
    ):
        """Rules produce dimension overrides at or above expected thresholds."""
        result = apply_rules(text)
        assert expected_dimension in result.dimension_overrides, (
            f"Expected '{expected_dimension}' in overrides for: {description}"
        )
        assert result.dimension_overrides[expected_dimension] >= min_score, (
            f"Expected {expected_dimension} >= {min_score}, "
            f"got {result.dimension_overrides[expected_dimension]} for: {description}"
        )

    def test_clean_text_fires_no_rules(self, sample_good_text):
        """Clean, high-quality text should not trigger any rules."""
        result = apply_rules(sample_good_text)
        assert result.matched_rules == []
        assert result.dimension_overrides == {}
        assert result.confidence == {}

    def test_empty_text_returns_empty_result(self):
        """Empty string returns an empty RuleResult without errors."""
        result = apply_rules("")
        assert isinstance(result, RuleResult)
        assert result.matched_rules == []
        assert result.dimension_overrides == {}

    def test_combined_signals_multiple_categories(self):
        """Text with both scam and emotional manipulation signals fires both."""
        text = "震惊！！！！！！日入过万！！！躺赚财富自由！！！再不加微信就晚了！！！"
        result = apply_rules(text)
        assert "scam_prob" in result.dimension_overrides
        assert "emotional_manipulation" in result.dimension_overrides
        assert len(result.matched_rules) >= 2

    def test_confidence_values_are_between_0_and_1(self, sample_junk_text):
        """All confidence values should be in the valid range [0, 1]."""
        result = apply_rules(sample_junk_text)
        for dim, conf in result.confidence.items():
            assert 0 <= conf <= 1, f"Confidence for {dim} out of range: {conf}"
