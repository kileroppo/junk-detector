"""Tests for src/core/recommendations.py - Actionable recommendations."""

from src.core.recommendations import get_recommendation


class TestScamRecommendation:
    """High scam_prob should recommend not clicking links."""

    def test_scam_high(self):
        result = get_recommendation(verdict="scam", scam_prob=80)
        assert result == "建议：不要点击链接，不要转账，可向12315举报"

    def test_scam_threshold(self):
        result = get_recommendation(verdict="scam", scam_prob=60)
        assert result == "建议：不要点击链接，不要转账，可向12315举报"


class TestAdvertorialRecommendation:
    """High advertorial_prob should warn about paid ads."""

    def test_advertorial_high(self):
        result = get_recommendation(verdict="advertorial", advertorial_prob=70)
        assert result == "建议：注意文中推荐可能是付费广告"

    def test_advertorial_threshold(self):
        result = get_recommendation(verdict="advertorial", advertorial_prob=60)
        assert result == "建议：注意文中推荐可能是付费广告"


class TestQualityRecommendation:
    """High overall_score should celebrate quality content."""

    def test_quality_high(self):
        result = get_recommendation(verdict="quality", overall_score=85)
        assert result == "🌟 优质内容！论证严密，数据翔实。建议：可以放心分享给朋友"

    def test_quality_above_80(self):
        result = get_recommendation(verdict="quality", overall_score=81)
        assert result == "🌟 优质内容！论证严密，数据翔实。建议：可以放心分享给朋友"


class TestSuspiciousRecommendation:
    """Default case should recommend cross-verification."""

    def test_default_suspicious(self):
        result = get_recommendation(verdict="suspicious")
        assert result == "建议：谨慎对待文中观点，建议交叉验证信息来源"

    def test_low_scores_no_flags(self):
        result = get_recommendation(
            verdict="unknown", scam_prob=30, advertorial_prob=40, overall_score=50
        )
        assert result == "建议：谨慎对待文中观点，建议交叉验证信息来源"


class TestPriorityOrder:
    """Scam takes priority over advertorial, which takes priority over quality."""

    def test_scam_overrides_advertorial(self):
        result = get_recommendation(
            verdict="mixed", scam_prob=80, advertorial_prob=80, overall_score=90
        )
        assert "不要点击链接" in result

    def test_advertorial_overrides_quality(self):
        result = get_recommendation(
            verdict="mixed", scam_prob=30, advertorial_prob=70, overall_score=90
        )
        assert "付费广告" in result
