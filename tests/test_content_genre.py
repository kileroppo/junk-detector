"""Tests for content genre detection and roundup calibration."""

from __future__ import annotations

from src.core.content_genre import (
    GENRE_ROUNDUP,
    apply_genre_calibration_v2,
    calculate_roundup_overall,
    compute_reference_value_score,
    detect_content_genre,
    finalize_roundup_dimensions,
    filter_roundup_labels,
    sanitize_roundup_summary,
)
from src.core.rules import apply_rules
from src.core.scorer import _calculate_overall
from src.core.config import load_config
from src.extractors.web import _trim_article_boilerplate
from src.models.score import DimensionScores


ROUNDUP_SAMPLE = """
Claude Code UI/UX 设计最佳 18 款 Skill:完整指南
1. Anthropic Frontend Design(官方 Skill)
仓库: github.com/anthropics/claude-code
安装: claude plugin add anthropic/frontend-design
2. UI/UX Pro Max - 完整设计数据库
仓库: github.com/nextlevelbuilder/ui-ux-pro-max-skill
安装: /plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill
3. Taste Skill
仓库: github.com/Leonxlnx/taste-skill
安装: npx skills add https://github.com/Leonxlnx/taste-skill
4. Interface Design
5. Frontend Design Pro Demo
6. Designer Skills
7. Bencium UX Designer
8. Vercel Agent Skills
9. Refactoring UI
对比表:应该选哪款 Skill?
"""


class TestDetectContentGenre:
    def test_roundup_detected(self):
        assert detect_content_genre(ROUNDUP_SAMPLE) == GENRE_ROUNDUP

    def test_short_text_default(self):
        assert detect_content_genre("hello") == "default"


class TestApplyGenreCalibration:
    def test_roundup_raises_info_density_floor(self):
        dims = DimensionScores(
            originality=20,
            info_density=10,
            reasoning_quality=5,
            readability=60,
            timeliness=40,
            ai_generated_prob=85,
            emotional_manipulation=10,
            advertorial_prob=70,
            scam_prob=30,
        )
        calibrated = apply_genre_calibration_v2(dims, GENRE_ROUNDUP, ROUNDUP_SAMPLE)
        assert calibrated.info_density >= 45
        assert calibrated.reasoning_quality >= 32
        assert calibrated.ai_generated_prob <= 68
        assert calibrated.advertorial_prob <= 58

    def test_screenshot_like_score_in_reference_band(self):
        dims = DimensionScores(
            originality=20,
            info_density=10,
            reasoning_quality=5,
            readability=60,
            timeliness=40,
            ai_generated_prob=85,
            emotional_manipulation=10,
            advertorial_prob=70,
            scam_prob=30,
        )
        cfg = load_config()
        before = _calculate_overall(dims, cfg)
        after = calculate_roundup_overall(
            finalize_roundup_dimensions(dims, ROUNDUP_SAMPLE), cfg
        )
        assert before < 40
        assert 52 <= after <= 68

    def test_reference_value_score_high_for_roundup_sample(self):
        assert compute_reference_value_score(ROUNDUP_SAMPLE) >= 55

    def test_sanitize_roundup_summary(self):
        harsh = "标题夸大，内容空洞，疑似AI生成的软文或SEO垃圾内容"
        dims = DimensionScores(
            originality=20,
            info_density=50,
            reasoning_quality=32,
            readability=60,
            timeliness=50,
            ai_generated_prob=68,
            emotional_manipulation=10,
            advertorial_prob=58,
            scam_prob=30,
        )
        out = sanitize_roundup_summary(harsh, dims)
        assert "SEO" not in out or "速查" in out
        assert "选型" in out or "清单" in out

    def test_filter_roundup_labels_drops_ai_and_advertorial(self):
        labels = filter_roundup_labels(["可能AI生成", "疑似软文", "高质量原创"])
        assert "可能AI生成" not in labels
        assert "疑似软文" not in labels
        assert "汇编参考" in labels


class TestScamKeywordFalsePositives:
    def test_ui_hierarchy_not_scam(self):
        text = "redesign-skill 审计已有 UI，并优化布局、间距、层级与样式决策。"
        result = apply_rules(text)
        assert "scam_prob" not in result.dimension_overrides

    def test_product_launch_not_scam(self):
        text = "UX Heuristics 适合上线前可用性审计与启发式检查。"
        result = apply_rules(text)
        assert "scam_prob" not in result.dimension_overrides


class TestArticleBoilerplateTrim:
    def test_strips_accessibility_chrome(self):
        raw = "跳到内容\n无障碍设置\n浅色主题\nZH\nIT\nEN\nClaude Code 指南正文\ngithub.com/foo\n"
        cleaned = _trim_article_boilerplate(raw)
        assert "跳到内容" not in cleaned
        assert "无障碍" not in cleaned
        assert "Claude Code 指南正文" in cleaned

    def test_truncates_at_related_articles(self):
        raw = "正文第一段\n对比表在此\n相关文章\n另一篇推荐\n"
        cleaned = _trim_article_boilerplate(raw)
        assert "正文第一段" in cleaned
        assert "另一篇推荐" not in cleaned
