"""Tests for src/core/fast_classifier.py — fast content classification."""

from __future__ import annotations

import pytest

from src.core.fast_classifier import (
    ClassifierResult,
    classify_fast,
    extract_features,
)


class TestExtractFeatures:
    """Tests for extract_features."""

    def test_returns_expected_keys(self):
        """extract_features returns a dict with expected feature keys."""
        features = extract_features("Hello world, this is a test.")

        assert "char_count" in features
        assert "word_count" in features
        assert "line_count" in features
        assert "scam_keyword_count" in features
        assert "ad_keyword_count" in features
        assert "emotional_pattern_count" in features
        assert "sentence_count" in features
        assert "char_diversity" in features

    def test_counts_scam_keywords(self):
        """extract_features detects scam keywords."""
        text = "日入过万！限时免费！躺赚财富自由！"
        features = extract_features(text)

        assert features["scam_keyword_count"] >= 3

    def test_counts_ad_keywords(self):
        """extract_features detects ad keywords."""
        text = "推荐码ABCD，扫码关注公众号获取优惠券"
        features = extract_features(text)

        assert features["ad_keyword_count"] >= 3

    def test_counts_emotional_patterns(self):
        """extract_features detects emotional patterns."""
        text = "震惊！！！必看！！！不转不是中国人！！！"
        features = extract_features(text)

        assert features["emotional_pattern_count"] >= 2

    def test_counts_ai_patterns(self):
        """extract_features detects AI-generated patterns."""
        text = "综上所述，总而言之，值得注意的是，这些内容需要指出的是很重要的。"
        features = extract_features(text)

        assert features["ai_pattern_count"] >= 3

    def test_char_count_and_word_count(self):
        """extract_features computes char_count and word_count correctly."""
        text = "一二三四五"
        features = extract_features(text)

        assert features["char_count"] == 5
        assert features["word_count"] == 1

    def test_empty_text(self):
        """extract_features handles empty text without errors."""
        features = extract_features("")

        assert features["char_count"] == 0
        assert features["word_count"] == 0


class TestClassifyFast:
    """Tests for classify_fast."""

    def test_returns_classifier_result(self):
        """classify_fast returns a ClassifierResult."""
        result = classify_fast("Some neutral content here.")

        assert isinstance(result, ClassifierResult)
        assert 0 <= result.predicted_score <= 100
        assert 0 <= result.confidence <= 1
        assert result.category in ("junk", "low", "medium", "good")

    def test_scam_content_classified_as_junk(self):
        """classify_fast labels scam content as junk."""
        text = "日入过万！躺赚财富自由！限时免费加微信领取秘籍！私聊领取！"
        result = classify_fast(text)

        assert result.category == "junk"
        assert result.predicted_score < 30

    def test_high_quality_content_classified_higher(self):
        """classify_fast gives better score to long, clean content."""
        # Long content with multiple paragraphs, no spam signals
        text = "人工智能技术的发展\n" * 100 + "\n".join(
            [f"这是第{i}段有意义的内容，探讨了技术发展的方向。" for i in range(10)]
        )
        result = classify_fast(text)

        assert result.predicted_score >= 50

    def test_very_short_content_classified_low(self):
        """classify_fast classifies very short text as junk."""
        result = classify_fast("hi")

        assert result.category == "junk"
        assert result.predicted_score < 30

    def test_should_skip_llm_with_high_confidence(self):
        """classify_fast sets should_skip_llm=True for high confidence predictions."""
        # Scam text with very high confidence
        text = "日入过万！躺赚！限时免费！私聊领取！财富自由！月入百万！"
        result = classify_fast(text, confidence_threshold=0.85)

        if result.confidence >= 0.85:
            assert result.should_skip_llm is True

    def test_neutral_content_lower_confidence(self):
        """classify_fast has lower confidence for neutral content."""
        text = "这是一段普通的新闻报道内容，没有特别的标志性词汇。" * 3
        result = classify_fast(text)

        # Neutral content should not have very high confidence
        assert result.confidence <= 0.9
