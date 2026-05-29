"""Tests for fact-credibility rules (unverifiable claims, fake authority, conspiracy patterns).

Verifies that credibility-related patterns correctly trigger scam_prob boosts
with appropriate thresholds based on hit count.
"""

from __future__ import annotations

import pytest

from src.core.rules import apply_rules


class TestCredibilityRules:
    """Parametrized tests for credibility rule detection."""

    @pytest.mark.parametrize(
        "text,min_scam_prob,description",
        [
            # 3+ hits triggers scam_prob >= 85
            (
                "据内部消息，知情人士透露，独家爆料这个项目有问题",
                85,
                "3 unverifiable claims triggers scam_prob >= 85",
            ),
            (
                "据内部消息称，专家表示这个很好，真相是背后有阴谋",
                85,
                "3 hits across different lists triggers scam_prob >= 85",
            ),
            (
                "央视报道专家表示研究表明这个药物有效",
                85,
                "3 fake authority patterns triggers scam_prob >= 85",
            ),
            (
                "真相是他们不想让你知道细思极恐的事情",
                85,
                "3 conspiracy patterns triggers scam_prob >= 85",
            ),
            # 2 hits triggers scam_prob >= 70
            (
                "据内部消息，知情人士透露这件事很严重",
                70,
                "2 unverifiable claims triggers scam_prob >= 70",
            ),
            (
                "专家表示研究表明这个方法有效",
                70,
                "2 fake authority patterns triggers scam_prob >= 70",
            ),
            (
                "真相是他们不想让你知道这个秘密",
                70,
                "2 conspiracy patterns triggers scam_prob >= 70",
            ),
            # 1 hit triggers scam_prob >= 55
            (
                "据内部消息，今天天气不错适合出门散步",
                55,
                "1 unverifiable claim triggers scam_prob >= 55",
            ),
            (
                "真相是这件事没那么简单",
                55,
                "1 conspiracy pattern triggers scam_prob >= 55",
            ),
            (
                "专家表示这个产品安全无害",
                55,
                "1 fake authority triggers scam_prob >= 55",
            ),
        ],
        ids=[
            "3_unverifiable_claims",
            "3_mixed_hits",
            "3_fake_authority",
            "3_conspiracy",
            "2_unverifiable_claims",
            "2_fake_authority",
            "2_conspiracy",
            "1_unverifiable_claim",
            "1_conspiracy",
            "1_fake_authority",
        ],
    )
    def test_credibility_triggers_scam_prob(self, text, min_scam_prob, description):
        """Credibility patterns produce scam_prob at or above expected thresholds."""
        result = apply_rules(text)
        assert "scam_prob" in result.dimension_overrides, (
            f"Expected scam_prob in overrides for: {description}"
        )
        assert result.dimension_overrides["scam_prob"] >= min_scam_prob, (
            f"Expected scam_prob >= {min_scam_prob}, "
            f"got {result.dimension_overrides['scam_prob']} for: {description}"
        )

    def test_credibility_rule_name_in_matched_rules(self):
        """Credibility rule appends 'credibility_unverifiable' to matched_rules."""
        text = "据内部消息，这件事情很重要"
        result = apply_rules(text)
        assert "credibility_unverifiable" in result.matched_rules

    def test_clean_academic_text_no_credibility_trigger(self):
        """Clean academic text does NOT trigger credibility rules."""
        text = (
            "本研究通过对500名受试者进行双盲实验，发现新药物在降低血压方面"
            "具有统计学显著效果(p<0.001)。实验组的平均收缩压下降了15mmHg，"
            "而对照组仅下降了3mmHg。结果发表于《中华医学杂志》2024年第3期。"
        )
        result = apply_rules(text)
        assert "credibility_unverifiable" not in result.matched_rules

    def test_clean_news_report_no_trigger(self):
        """Properly sourced news report does NOT trigger credibility rules."""
        text = (
            "根据国家统计局今日发布的数据，2024年第一季度GDP同比增长5.3%。"
            "其中第三产业贡献最大，增速达到6.1%。分析人士认为，这表明经济"
            "复苏态势良好，消费市场逐步回暖。"
        )
        result = apply_rules(text)
        assert "credibility_unverifiable" not in result.matched_rules

    def test_credibility_additive_to_existing_scam_score(self):
        """Credibility boost is additive to existing scam_prob from scam keywords."""
        text = "日入过万！据内部消息，知情人士透露，独家爆料这个项目能躺赚"
        result = apply_rules(text)
        # scam_keywords fires (3+ keywords: 日入过万, 躺赚, + others)
        # credibility fires (3 hits: 据内部消息, 知情人士透露, 独家爆料)
        # Combined should be capped at 100
        assert result.dimension_overrides["scam_prob"] == 100.0

    def test_credibility_scam_prob_capped_at_100(self):
        """Combined scam + credibility score is capped at 100."""
        text = (
            "日入过万躺赚财富自由！据内部消息，知情人士透露，"
            "独家爆料这个项目稳赚不赔"
        )
        result = apply_rules(text)
        assert result.dimension_overrides["scam_prob"] <= 100.0
