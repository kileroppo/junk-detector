"""Tests for the content violation pre-filter (src.core.content_filter).

Verifies that obvious violation categories are detected before LLM scoring.
Uses parametrize to cover all violation types.
"""
from __future__ import annotations

import pytest

from src.core.content_filter import FilterResult, check_content


class TestCheckContent:
    """Parametrized tests for check_content() filter."""

    @pytest.mark.parametrize(
        "text,should_pass,expected_type,description",
        [
            # Clean text passes
            (
                "这是一篇关于技术发展的优质文章，讨论了人工智能的最新进展。",
                True,
                None,
                "clean technical text passes filter",
            ),
            # Gambling - 2+ keywords rejected
            (
                "网上赌场提供最好的在线博彩服务，百家乐玩家首选",
                False,
                "赌博",
                "2+ gambling keywords are rejected",
            ),
            # Pornographic - 1 keyword rejected
            (
                "这个平台提供约炮服务和裸聊功能",
                False,
                "色情",
                "pornographic keywords rejected",
            ),
            # Violence - 1 keyword rejected
            (
                "教你如何制作炸弹的详细教程",
                False,
                "暴力/恐怖",
                "violence keywords rejected",
            ),
            # Drug-related - 1 keyword rejected
            (
                "本店代购冰毒快递到家",
                False,
                "毒品",
                "drug keywords rejected",
            ),
            # Phishing - phrase + URL rejected
            (
                "验证您的账号 请点击 https://fake-bank.com/verify 完成验证",
                False,
                "钓鱼",
                "phishing phrase + URL rejected",
            ),
            # Single gambling keyword passes (needs 2)
            (
                "百家乐是一种很受欢迎的纸牌游戏",
                True,
                None,
                "single gambling keyword passes (threshold is 2)",
            ),
            # Phishing phrase without URL passes
            (
                "验证您的账号信息是否正确",
                True,
                None,
                "phishing phrase without URL passes",
            ),
            # Empty text passes
            (
                "",
                True,
                None,
                "empty text passes filter",
            ),
        ],
        ids=[
            "clean_text_passes",
            "gambling_rejected",
            "pornographic_rejected",
            "violence_rejected",
            "drugs_rejected",
            "phishing_rejected",
            "single_gambling_passes",
            "phishing_no_url_passes",
            "empty_passes",
        ],
    )
    def test_content_filter(self, text, should_pass, expected_type, description):
        """Content filter correctly identifies violations and passes clean text."""
        result = check_content(text)
        assert result.passed is should_pass, f"Failed: {description}"
        if not should_pass:
            assert result.violation_type == expected_type

    def test_filter_result_has_matched_patterns(self):
        """When filter rejects content, it includes the matched pattern details."""
        result = check_content("网上赌场在线博彩赌球开奖结果")
        assert result.passed is False
        assert len(result.matched_patterns) >= 2

    def test_filter_short_circuits_on_first_violation(self):
        """Filter returns the first violation found (ordered by severity)."""
        # Text with both violence and gambling
        text = "制作炸弹教程，同时提供网上赌场在线博彩服务"
        result = check_content(text)
        assert result.passed is False
        # Violence is checked before gambling in the source
        assert result.violation_type == "暴力/恐怖"
