"""Tests for negation context detection in the rules engine.

Verifies that keywords appearing in analytical/warning context (e.g., articles
ABOUT detecting scams) receive reduced scores compared to actual scam content.
"""

from __future__ import annotations

import pytest

from src.core.rules import apply_rules, _has_negation_context


class TestNegationContextFunction:
    """Unit tests for _has_negation_context helper."""

    def test_negation_keyword_before_match(self):
        """Negation keyword within 20 chars before match is detected."""
        content = "如何识别日入过万的骗局"
        # "日入过万" starts at index 4
        assert _has_negation_context(content, 4, 8) is True

    def test_negation_keyword_after_match(self):
        """Negation keyword within 20 chars after match is detected."""
        content = "日入过万的套路分析"
        # "日入过万" starts at index 0
        assert _has_negation_context(content, 0, 4) is True

    def test_no_negation_keyword_nearby(self):
        """No negation keyword within window returns False."""
        content = "日入过万零成本加微信"
        assert _has_negation_context(content, 0, 4) is False

    def test_negation_keyword_too_far_away(self):
        """Negation keyword beyond 20 chars does NOT count."""
        # Put 25+ chars of padding between negation keyword and match
        content = "识别" + "一" * 25 + "日入过万"
        match_start = content.index("日入过万")
        match_end = match_start + 4
        assert _has_negation_context(content, match_start, match_end) is False


class TestScamNegationContext:
    """Tests that scam keywords in analytical context get reduced scores."""

    def test_negated_scam_lower_than_plain_scam(self):
        """'如何识别日入过万的骗局' has lower scam_prob than '日入过万零成本加微信'."""
        negated = apply_rules("如何识别日入过万的骗局")
        plain = apply_rules("日入过万零成本加微信")

        # Plain text has 3 scam keywords (日入过万, 零成本, 加微信) -> 95
        assert "scam_prob" in plain.dimension_overrides
        assert plain.dimension_overrides["scam_prob"] >= 95

        # Negated text has 1 keyword (日入过万) with negation context -> 0.25 hit -> None
        # OR it might still fire at lower level
        negated_score = negated.dimension_overrides.get("scam_prob", 0)
        plain_score = plain.dimension_overrides["scam_prob"]
        assert negated_score < plain_score

    def test_defense_guide_lower_than_scam_content(self):
        """'防骗指南：警惕财富自由骗局' lower than '财富自由限时免费'."""
        negated = apply_rules("防骗指南：警惕财富自由骗局")
        plain = apply_rules("财富自由限时免费")

        # Plain has 2 keywords (财富自由, 限时免费) -> 75
        assert "scam_prob" in plain.dimension_overrides

        negated_score = negated.dimension_overrides.get("scam_prob", 0)
        plain_score = plain.dimension_overrides["scam_prob"]
        assert negated_score < plain_score

    def test_multiple_negated_keywords_still_reduced(self):
        """Multiple scam keywords all with negation context produce lower score."""
        # All keywords have negation context
        negated = apply_rules("防骗分析：识别日入过万和躺赚的套路")
        # Same keywords without negation
        plain = apply_rules("日入过万躺赚财富自由")

        negated_score = negated.dimension_overrides.get("scam_prob", 0)
        plain_score = plain.dimension_overrides.get("scam_prob", 0)
        assert negated_score < plain_score

    def test_mixed_negated_and_plain_intermediate_score(self):
        """Content with both negated and non-negated keywords has intermediate score."""
        # "识别" negates "日入过万" nearby, but "月入百万" and "零成本" are far from negation
        mixed = apply_rules("识别日入过万骗局的这篇长文章详细介绍了各种各样的手段，比如月入百万还有零成本全是假的")
        # Pure scam: 3+ keywords non-negated -> 95
        plain = apply_rules("日入过万零成本加微信")

        mixed_score = mixed.dimension_overrides.get("scam_prob", 0)
        plain_score = plain.dimension_overrides.get("scam_prob", 0)

        # Mixed should fire (月入百万 + 零成本 far from negation count as full hits)
        assert "scam_prob" in mixed.dimension_overrides
        assert mixed_score <= plain_score


class TestEmotionalNegationContext:
    """Tests that emotional manipulation keywords in analytical context get reduced scores."""

    def test_emotional_analysis_reduced(self):
        """'防范情绪操纵的方法：震惊是怎么被利用的' reduces emotional scores."""
        negated = apply_rules("防范情绪操纵的方法：震惊是怎么被利用的")
        plain = apply_rules("震惊！！！！！！必看！！！！！！")

        # Plain text has excessive punctuation + anxiety phrases -> high score
        assert "emotional_manipulation" in plain.dimension_overrides

        negated_score = negated.dimension_overrides.get("emotional_manipulation", 0)
        plain_score = plain.dimension_overrides["emotional_manipulation"]
        assert negated_score < plain_score

    def test_anxiety_analysis_article(self):
        """Article analyzing FOMO tactics should not trigger high emotional score."""
        analysis = apply_rules("研究分析：'再不买就晚了'这类话术如何制造焦虑")
        # The negation keyword "研究" and "分析" should reduce impact
        analysis_score = analysis.dimension_overrides.get("emotional_manipulation", 0)
        # Should not reach the high threshold of 85
        assert analysis_score < 85


class TestAdvertorialNegationContext:
    """Tests that advertorial keywords in analytical context get reduced scores."""

    def test_advertorial_analysis_reduced(self):
        """'揭露软文套路分析' reduces advertorial scores."""
        negated = apply_rules("揭露软文套路分析：种草和好物推荐的本质")
        plain = apply_rules("种草好物推荐闭眼入")

        # Plain should trigger advertorial
        assert "advertorial_prob" in plain.dimension_overrides

        negated_score = negated.dimension_overrides.get("advertorial_prob", 0)
        plain_score = plain.dimension_overrides["advertorial_prob"]
        assert negated_score < plain_score

    def test_far_negation_does_not_reduce(self):
        """Negation keyword far away (>20 chars) does NOT reduce advertorial scores."""
        # "揭露" is more than 20 chars away from both "推荐码" and "优惠券"
        padding = "这是一段非常非常非常非常非常非常长的填充文字内容"
        far_negation = apply_rules("揭露" + padding + "推荐码注册优惠券")
        plain = apply_rules("推荐码注册优惠券")

        far_score = far_negation.dimension_overrides.get("advertorial_prob", 0)
        plain_score = plain.dimension_overrides.get("advertorial_prob", 0)
        # Far negation should NOT reduce, so scores should be equal
        assert far_score >= plain_score
