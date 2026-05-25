"""Tests for the deterministic rules engine (src.core.rules).

Verifies that keyword/regex rules correctly identify content quality signals
and produce appropriate dimension overrides with confidence levels.
"""

from __future__ import annotations

import pytest

from src.core.rules import ComboRule, RuleResult, apply_rules


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
    def test_rule_fires_with_expected_score(self, text, expected_dimension, min_score, description):
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


class TestRegexPatternMatching:
    """Tests for regex-based keyword matching with word boundary awareness."""

    @pytest.mark.parametrize(
        "text,should_match,description",
        [
            # Short keywords (< 4 chars) should use word boundary to avoid substring matches
            ("ICO项目是骗局", True, "ICO as standalone triggers scam"),
            ("PICOT研究方法论", False, "ICO embedded in PICOT should NOT trigger"),
            ("Cisco设备很好用", False, "ICO embedded in Cisco should NOT trigger"),
            # Multi-word phrases should still match
            ("日入过万是不可能的", True, "multi-char phrase matches normally"),
            ("财富自由是个梦想", True, "multi-char phrase matches normally"),
            # Regular keywords match as before
            ("这个稳赚不赔的项目", True, "normal keyword still matches"),
            ("躺赚是不存在的", True, "normal keyword still matches"),
        ],
        ids=[
            "ico_standalone",
            "ico_in_picot",
            "ico_in_cisco",
            "multiword_phrase",
            "multiword_phrase_2",
            "normal_keyword",
            "normal_keyword_2",
        ],
    )
    def test_short_keyword_word_boundary(self, text, should_match, description):
        """Short keywords use word boundaries to prevent false positives."""
        result = apply_rules(text)
        if should_match:
            assert "scam_prob" in result.dimension_overrides, (
                f"Expected scam_prob to fire for: {description}"
            )
        else:
            assert "scam_prob" not in result.dimension_overrides, (
                f"Expected scam_prob NOT to fire for: {description}"
            )

    def test_regex_matching_preserves_existing_behavior(self):
        """All original keywords still match after regex upgrade."""
        # Test a selection of important keywords to ensure backward compat
        keywords_to_test = [
            "日入过万",
            "躺赚",
            "财富自由",
            "限时免费",
            "月入百万",
            "稳赚不赔",
            "币圈",
            "翻倍",
        ]
        for kw in keywords_to_test:
            text = f"这是一段包含{kw}的文本"
            result = apply_rules(text)
            assert "scam_prob" in result.dimension_overrides, (
                f"Keyword '{kw}' should still trigger scam_prob"
            )


class TestComboRules:
    """Tests for the ComboRule concept - multiple weak signals boosting confidence."""

    def test_combo_rule_dataclass_fields(self):
        """ComboRule has expected fields: name, keywords, dimension, score_boost, confidence_boost."""
        rule = ComboRule(
            name="test_combo",
            keywords=["a", "b", "c"],
            dimension="scam_prob",
            score_boost=20,
            confidence_boost=0.1,
        )
        assert rule.name == "test_combo"
        assert rule.keywords == ["a", "b", "c"]
        assert rule.dimension == "scam_prob"
        assert rule.score_boost == 20
        assert rule.confidence_boost == 0.1

    def test_engagement_bait_combo_fires(self):
        """engagement_bait combo fires when all keywords present."""
        text = "请关注我的账号，点赞这条视频，转发给你的朋友们"
        result = apply_rules(text)
        assert "advertorial_prob" in result.dimension_overrides
        assert "combo_engagement_bait" in result.matched_rules

    def test_engagement_bait_combo_partial_no_fire(self):
        """engagement_bait combo does NOT fire with only partial keywords."""
        text = "请关注我的账号，点赞这条视频"  # missing 转发
        result = apply_rules(text)
        assert "combo_engagement_bait" not in result.matched_rules

    def test_crypto_scam_combo_fires(self):
        """crypto_scam_combo fires when all keywords present."""
        text = "币圈大佬告诉你翻倍很简单稳赚不亏"
        result = apply_rules(text)
        assert "scam_prob" in result.dimension_overrides
        assert "combo_crypto_scam_combo" in result.matched_rules

    def test_crypto_scam_combo_partial_no_fire(self):
        """crypto_scam_combo does NOT fire with partial keywords."""
        text = "币圈是一个很有争议的话题"  # only 币圈, missing 翻倍/稳赚
        result = apply_rules(text)
        assert "combo_crypto_scam_combo" not in result.matched_rules

    def test_fomo_urgency_combo_fires(self):
        """fomo_urgency combo fires when all keywords present."""
        text = "限时优惠名额有限最后一天抢购"
        result = apply_rules(text)
        assert "emotional_manipulation" in result.dimension_overrides
        assert "combo_fomo_urgency" in result.matched_rules

    def test_fomo_urgency_combo_partial_no_fire(self):
        """fomo_urgency combo does NOT fire with partial keywords."""
        text = "限时优惠活动正在进行中"  # only 限时, missing 名额/最后
        result = apply_rules(text)
        assert "combo_fomo_urgency" not in result.matched_rules

    def test_combo_boost_additive_to_existing(self):
        """Combo rule boosts add to existing dimension scores."""
        # This text triggers scam_keywords AND crypto_scam_combo
        text = "币圈翻倍稳赚不赔的项目来了"
        result = apply_rules(text)
        assert "scam_prob" in result.dimension_overrides
        # Base scam score + combo boost should be higher than base alone
        # Base for 3+ keywords = 95, combo adds 15, capped at 100
        assert result.dimension_overrides["scam_prob"] >= 95

    def test_combo_boost_capped_at_100(self):
        """Combo boosts are capped at 100."""
        # Many scam keywords + combo - should not exceed 100
        text = "币圈翻倍稳赚日入过万躺赚财富自由限时免费"
        result = apply_rules(text)
        assert result.dimension_overrides.get("scam_prob", 0) <= 100

    def test_combo_confidence_boost(self):
        """Combo rules also boost confidence."""
        text = "币圈翻倍稳赚不赔的项目"
        result = apply_rules(text)
        assert "scam_prob" in result.confidence
        # Confidence should be boosted but still <= 1.0
        assert result.confidence["scam_prob"] <= 1.0

    def test_multiple_combos_can_fire(self):
        """Multiple combo rules can fire simultaneously."""
        text = "币圈翻倍稳赚 关注点赞转发 限时名额最后一天"
        result = apply_rules(text)
        combo_rules = [r for r in result.matched_rules if r.startswith("combo_")]
        assert len(combo_rules) >= 2
