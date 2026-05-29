"""Tests for the verdict generator module (src.core.verdict_generator).

Verifies that the generate_verdict function produces correct verdicts,
actions, severity levels, and reading time estimates.
"""

from __future__ import annotations

import pytest

from src.core.verdict_generator import generate_verdict


class TestSeverityLevels:
    """Tests for severity classification based on overall_score."""

    def test_high_score_returns_safe(self):
        """Score > 75 returns severity='safe' with reading time in verdict."""
        result = generate_verdict(
            overall_score=80,
            dimensions={"scam_prob": 10, "emotional_manipulation": 5},
            content_type=None,
            content_text="这是一段高质量的文章内容" * 50,
        )
        assert result["severity"] == "safe"
        assert "分钟阅读" in result["verdict"]
        assert result["read_time_minutes"] >= 1

    def test_medium_score_returns_warning(self):
        """Score 40-75 returns severity='warning' with specific issue."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"scam_prob": 60, "emotional_manipulation": 30},
            content_type=None,
            content_text="一段中等质量文章",
        )
        assert result["severity"] == "warning"
        assert "建议批判性阅读" in result["verdict"]

    def test_low_score_returns_danger(self):
        """Score < 40 returns severity='danger' with warning based on highest risk."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"scam_prob": 90, "emotional_manipulation": 40},
            content_type=None,
            content_text="垃圾内容",
        )
        assert result["severity"] == "danger"
        assert "诈骗" in result["verdict"] or "收割" in result["verdict"]

    def test_boundary_score_76_is_safe(self):
        """Score exactly 76 (> 75) is safe."""
        result = generate_verdict(
            overall_score=76,
            dimensions={},
            content_type=None,
            content_text="测试",
        )
        assert result["severity"] == "safe"

    def test_boundary_score_75_is_warning(self):
        """Score exactly 75 (not > 75) is warning."""
        result = generate_verdict(
            overall_score=75,
            dimensions={},
            content_type=None,
            content_text="测试",
        )
        assert result["severity"] == "warning"

    def test_boundary_score_41_is_warning(self):
        """Score exactly 41 (> 40) is warning."""
        result = generate_verdict(
            overall_score=41,
            dimensions={},
            content_type=None,
            content_text="测试",
        )
        assert result["severity"] == "warning"

    def test_boundary_score_40_is_danger(self):
        """Score exactly 40 (not > 40) is danger."""
        result = generate_verdict(
            overall_score=40,
            dimensions={},
            content_type=None,
            content_text="测试",
        )
        assert result["severity"] == "danger"


class TestVerdictContent:
    """Tests for verdict message content."""

    def test_safe_verdict_includes_read_time(self):
        """Safe verdict includes reading time in minutes."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="字" * 800,  # 800 chars = 2 minutes
        )
        assert "2 分钟" in result["verdict"]

    def test_warning_with_high_scam_shows_sales_issue(self):
        """Warning with scam_prob > 50 shows sales-related issue."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"scam_prob": 60, "emotional_manipulation": 20},
            content_type=None,
            content_text="测试内容",
        )
        assert "推销" in result["verdict"]

    def test_warning_with_high_advertorial_shows_promo_issue(self):
        """Warning with advertorial_prob > 50 shows promotion issue."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"advertorial_prob": 65, "scam_prob": 20},
            content_type=None,
            content_text="测试内容",
        )
        assert "推广" in result["verdict"]

    def test_warning_with_high_emotional_shows_emotion_issue(self):
        """Warning with emotional_manipulation > 50 shows emotion issue."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"emotional_manipulation": 70, "scam_prob": 10},
            content_type=None,
            content_text="测试内容",
        )
        assert "情绪" in result["verdict"]

    def test_warning_with_high_ai_shows_ai_issue(self):
        """Warning with ai_generated_prob > 50 shows AI issue."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"ai_generated_prob": 65, "scam_prob": 10},
            content_type=None,
            content_text="测试内容",
        )
        assert "AI" in result["verdict"]

    def test_warning_with_low_risk_dims_shows_general(self):
        """Warning with all risk dims <= 50 shows general message."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"scam_prob": 30, "emotional_manipulation": 20},
            content_type=None,
            content_text="测试内容",
        )
        assert "内容质量一般" in result["verdict"]

    def test_danger_with_high_scam(self):
        """Danger with highest risk being scam shows scam warning."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"scam_prob": 95, "emotional_manipulation": 40},
            content_type=None,
            content_text="测试",
        )
        assert "诈骗" in result["verdict"] or "收割" in result["verdict"]

    def test_danger_with_high_advertorial(self):
        """Danger with highest risk being advertorial shows promo warning."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"advertorial_prob": 90, "scam_prob": 30},
            content_type=None,
            content_text="测试",
        )
        assert "推广" in result["verdict"]

    def test_danger_with_high_emotional(self):
        """Danger with highest risk being emotional shows emotional warning."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"emotional_manipulation": 90, "scam_prob": 30},
            content_type=None,
            content_text="测试",
        )
        assert "情绪" in result["verdict"]

    def test_danger_with_high_ai(self):
        """Danger with highest risk being AI shows AI warning."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"ai_generated_prob": 90, "scam_prob": 30},
            content_type=None,
            content_text="测试",
        )
        assert "AI" in result["verdict"]


class TestActionRecommendations:
    """Tests for action recommendations based on content type and risk."""

    def test_tool_list_safe_returns_tool_action(self):
        """content_type='tool_list' with high score returns tool_list action."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type="tool_list",
            content_text="工具列表" * 100,
        )
        assert "收藏" in result["action"]

    def test_news_safe_returns_news_action(self):
        """content_type='news' with high score returns news action."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type="news",
            content_text="新闻内容" * 100,
        )
        assert "信源" in result["action"]

    def test_safe_generic_returns_reading_time_action(self):
        """Safe generic content returns action with reading time."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="字" * 1200,  # 1200 chars = 3 min
        )
        assert "3 分钟" in result["action"]

    def test_danger_high_scam_returns_scam_action(self):
        """Danger with high scam_prob returns scam warning action."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"scam_prob": 90},
            content_type=None,
            content_text="测试",
        )
        assert "诈骗" in result["action"]

    def test_danger_high_advertorial_returns_promo_action(self):
        """Danger with high advertorial_prob returns advertorial action."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"advertorial_prob": 85},
            content_type=None,
            content_text="测试",
        )
        assert "推广" in result["action"]

    def test_danger_high_emotional_returns_emotional_action(self):
        """Danger with high emotional_manipulation returns emotional action."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"emotional_manipulation": 80},
            content_type=None,
            content_text="测试",
        )
        assert "冷静" in result["action"]

    def test_danger_high_ai_returns_ai_action(self):
        """Danger with high ai_generated_prob returns AI action."""
        result = generate_verdict(
            overall_score=20,
            dimensions={"ai_generated_prob": 80},
            content_type=None,
            content_text="测试",
        )
        assert "AI" in result["action"]

    def test_danger_low_risk_values_returns_generic_action(self):
        """Danger with no dimension > 70 returns generic action."""
        result = generate_verdict(
            overall_score=30,
            dimensions={"scam_prob": 50, "emotional_manipulation": 60},
            content_type=None,
            content_text="测试",
        )
        assert "不建议" in result["action"]

    def test_warning_high_advertorial_returns_promo_warning(self):
        """Warning with advertorial_prob > 50 returns specific action."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"advertorial_prob": 65},
            content_type=None,
            content_text="测试",
        )
        assert "推广" in result["action"] or "核心信息" in result["action"]

    def test_warning_high_emotional_returns_calm_action(self):
        """Warning with emotional_manipulation > 50 returns calm action."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"emotional_manipulation": 60},
            content_type=None,
            content_text="测试",
        )
        assert "冷静" in result["action"]

    def test_warning_generic_returns_reading_time(self):
        """Warning with low risk dims returns generic reading suggestion."""
        result = generate_verdict(
            overall_score=55,
            dimensions={"scam_prob": 30},
            content_type=None,
            content_text="字" * 400,  # 1 min
        )
        assert "分钟" in result["action"]


class TestReadingTime:
    """Tests for reading time calculation."""

    def test_800_chars_equals_2_minutes(self):
        """800 Chinese characters should take ~2 minutes at 400 chars/min."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="字" * 800,
        )
        assert result["read_time_minutes"] == 2

    def test_minimum_reading_time_is_1(self):
        """Very short content has minimum reading time of 1 minute."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="短",
        )
        assert result["read_time_minutes"] == 1

    def test_empty_content_reading_time_is_1(self):
        """Empty content has minimum reading time of 1."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="",
        )
        assert result["read_time_minutes"] == 1

    def test_1200_chars_equals_3_minutes(self):
        """1200 chars / 400 chars per min = 3 minutes."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="字" * 1200,
        )
        assert result["read_time_minutes"] == 3


class TestReturnStructure:
    """Tests for the return dict structure."""

    def test_returns_dict_with_all_keys(self):
        """Result contains verdict, action, severity, and read_time_minutes."""
        result = generate_verdict(
            overall_score=50,
            dimensions={},
            content_type=None,
            content_text="测试内容",
        )
        assert "verdict" in result
        assert "action" in result
        assert "severity" in result
        assert "read_time_minutes" in result

    def test_severity_is_valid_value(self):
        """Severity is one of: safe, warning, danger."""
        for score in [20, 55, 85]:
            result = generate_verdict(
                overall_score=score,
                dimensions={},
                content_type=None,
                content_text="测试",
            )
            assert result["severity"] in ("safe", "warning", "danger")

    def test_read_time_is_int(self):
        """read_time_minutes is always an integer."""
        result = generate_verdict(
            overall_score=85,
            dimensions={},
            content_type=None,
            content_text="字" * 500,
        )
        assert isinstance(result["read_time_minutes"], int)
