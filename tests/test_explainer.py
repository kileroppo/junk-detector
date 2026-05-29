"""Tests for src/core/explainer.py - Natural Language Explainer."""

from src.core.explainer import explain_result
from src.core.rules import RuleResult
from src.models.score import DimensionScores, ScoreResult


def _make_score_result(overall_score: float, **dim_overrides) -> ScoreResult:
    """Helper to create a ScoreResult with given overall_score and optional dimension overrides."""
    defaults = {
        "originality": 50,
        "info_density": 50,
        "reasoning_quality": 50,
        "readability": 50,
        "timeliness": 50,
        "ai_generated_prob": 0,
        "emotional_manipulation": 0,
        "advertorial_prob": 0,
        "scam_prob": 0,
    }
    defaults.update(dim_overrides)
    dims = DimensionScores(**defaults)
    return ScoreResult(
        overall_score=overall_score,
        dimensions=dims,
        labels=[],
        summary="test",
        rule_hits=[],
    )


class TestExplainHighScam:
    """High scam score should produce explanation mentioning scam keywords."""

    def test_scam_keywords_mentioned(self):
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 95.0},
            confidence={"scam_prob": 0.95},
        )
        score_result = _make_score_result(15.0, scam_prob=95.0)
        explanation = explain_result(score_result, rule_result)

        assert "\U0001f6a8" in explanation
        assert "诈骗" in explanation

    def test_scam_with_credibility(self):
        rule_result = RuleResult(
            matched_rules=["scam_keywords", "credibility_unverifiable"],
            dimension_overrides={"scam_prob": 95.0},
            confidence={"scam_prob": 0.95},
        )
        score_result = _make_score_result(10.0, scam_prob=95.0)
        explanation = explain_result(score_result, rule_result)

        assert "\U0001f6a8" in explanation
        assert "诈骗" in explanation
        assert "不可验证" in explanation

    def test_scam_quotes_keywords_from_content(self):
        """When content is provided, explanation should quote exact matched keywords."""
        content = "想要财富自由吗？加入我们的区块链投资群，日入过万不是梦！"
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 95.0},
            confidence={"scam_prob": 0.95},
        )
        score_result = _make_score_result(5.0, scam_prob=95.0)
        explanation = explain_result(score_result, rule_result, content=content)

        assert "\U0001f6a8" in explanation
        # Should quote at least one keyword from the content
        assert '"' in explanation
        # Should contain one of the matched keywords
        assert "财富自由" in explanation or "日入过万" in explanation or "区块链投资" in explanation

    def test_scam_line_numbers_with_multiline_content(self):
        """When content has newlines, line numbers should be present."""
        content = "第一行普通内容\n想要财富自由吗？\n日入过万不是梦！加微信领取"
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 95.0},
            confidence={"scam_prob": 0.95},
        )
        score_result = _make_score_result(5.0, scam_prob=95.0)
        explanation = explain_result(score_result, rule_result, content=content)

        assert "第" in explanation and "行" in explanation


class TestExplainAdvertorial:
    """High advertorial score should produce explanation mentioning promotion."""

    def test_advertorial_mentioned(self):
        rule_result = RuleResult(
            matched_rules=["advertorial_promo"],
            dimension_overrides={"advertorial_prob": 80.0},
            confidence={"advertorial_prob": 0.85},
        )
        score_result = _make_score_result(35.0, advertorial_prob=80.0)
        explanation = explain_result(score_result, rule_result)

        assert "\U0001f6a8" in explanation
        assert "商业推广" in explanation

    def test_advertorial_with_platform(self):
        rule_result = RuleResult(
            matched_rules=["advertorial_promo", "platform_wechat_patterns"],
            dimension_overrides={"advertorial_prob": 80.0},
            confidence={"advertorial_prob": 0.85},
        )
        score_result = _make_score_result(35.0, advertorial_prob=80.0)
        explanation = explain_result(score_result, rule_result)

        assert "平台营销" in explanation

    def test_advertorial_quotes_keywords(self):
        """When content is provided, explanation quotes matched advertorial keywords."""
        content = "亲测有效，回购无数次了，推荐码 BEAUTY20 还能打八折"
        rule_result = RuleResult(
            matched_rules=["advertorial_promo"],
            dimension_overrides={"advertorial_prob": 80.0},
            confidence={"advertorial_prob": 0.85},
        )
        score_result = _make_score_result(20.0, advertorial_prob=80.0)
        explanation = explain_result(score_result, rule_result, content=content)

        assert '"' in explanation
        assert "推荐码" in explanation or "亲测有效" in explanation or "回购无数次" in explanation


class TestExplainQualityContent:
    """Quality content (high overall score) should produce positive explanation."""

    def test_positive_explanation(self):
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        score_result = _make_score_result(85.0)
        explanation = explain_result(score_result, rule_result)

        assert "\u2705" in explanation
        assert "正常" in explanation

    def test_quality_content_mentions_positive_aspects(self):
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        score_result = _make_score_result(75.0)
        explanation = explain_result(score_result, rule_result)

        assert "\u2705" in explanation
        assert "论证清晰" in explanation or "信息密度" in explanation


class TestExplainBorderlineContent:
    """Borderline content (score 40-69) should produce cautious explanation."""

    def test_borderline_with_signals(self):
        rule_result = RuleResult(
            matched_rules=["emotional_anxiety_phrases"],
            dimension_overrides={"emotional_manipulation": 70.0},
            confidence={"emotional_manipulation": 0.75},
        )
        score_result = _make_score_result(55.0, emotional_manipulation=70.0)
        explanation = explain_result(score_result, rule_result)

        assert "\u26a0\ufe0f" in explanation
        assert "情绪操纵" in explanation

    def test_borderline_without_signals(self):
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        score_result = _make_score_result(50.0)
        explanation = explain_result(score_result, rule_result)

        # Honest uncertainty messaging for borderline cases with few signals
        assert "\U0001f914" in explanation
        assert "信号不够明确" in explanation


class TestExplainEmptyRules:
    """Empty or no rule hits should produce generic explanation."""

    def test_empty_rules_high_score(self):
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        score_result = _make_score_result(80.0)
        explanation = explain_result(score_result, rule_result)

        assert "\u2705" in explanation
        assert explanation != ""

    def test_empty_rules_low_score(self):
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        score_result = _make_score_result(20.0)
        explanation = explain_result(score_result, rule_result)

        assert "\U0001f6a8" in explanation
        assert "未匹配" in explanation or "人工复查" in explanation

    def test_empty_rules_mid_score(self):
        rule_result = RuleResult(
            matched_rules=[],
            dimension_overrides={},
            confidence={},
        )
        score_result = _make_score_result(55.0)
        explanation = explain_result(score_result, rule_result)

        assert "\u26a0\ufe0f" in explanation


class TestExplainAIGenerated:
    """AI-generated signals should be mentioned."""

    def test_ai_generated_in_explanation(self):
        rule_result = RuleResult(
            matched_rules=["ai_generated_signals"],
            dimension_overrides={"ai_generated_prob": 65.0},
            confidence={"ai_generated_prob": 0.6},
        )
        score_result = _make_score_result(55.0, ai_generated_prob=65.0)
        explanation = explain_result(score_result, rule_result)

        assert "AI生成" in explanation


class TestExplainWithContent:
    """Tests for the content-aware keyword quoting feature."""

    def test_no_content_still_works(self):
        """Backward compatibility: explain_result works without content."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 95.0},
            confidence={"scam_prob": 0.95},
        )
        score_result = _make_score_result(5.0, scam_prob=95.0)
        explanation = explain_result(score_result, rule_result)

        assert "\U0001f6a8" in explanation
        assert "诈骗" in explanation

    def test_emotional_quotes_anxiety_phrases(self):
        """Emotional manipulation explanation quotes anxiety phrases."""
        content = "震惊！再不看就晚了！转发救人一命！"
        rule_result = RuleResult(
            matched_rules=["emotional_anxiety_and_punctuation"],
            dimension_overrides={"emotional_manipulation": 85.0},
            confidence={"emotional_manipulation": 0.9},
        )
        score_result = _make_score_result(15.0, emotional_manipulation=85.0)
        explanation = explain_result(score_result, rule_result, content=content)

        assert '"' in explanation
        assert "震惊" in explanation or "再不" in explanation
