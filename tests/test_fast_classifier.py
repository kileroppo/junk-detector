"""Tests for src/core/fast_classifier.py — fast content classification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.fast_classifier import (
    ClassifierResult,
    _try_ml_model,
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

    def test_text_with_only_numbers_has_high_number_ratio(self):
        """extract_features returns high number_ratio for numeric text."""
        text = "123 456 789 012 345 678 901 234"
        features = extract_features(text)

        assert features["number_ratio"] >= 1.0

    def test_text_with_many_urls_has_high_link_count(self):
        """extract_features detects multiple URLs."""
        text = (
            "http://example.com http://foo.bar http://baz.qux "
            "https://a.com https://b.com"
        )
        features = extract_features(text)

        assert features["link_count"] == 5

    def test_multiline_text_with_markdown_headings_has_title(self):
        """extract_features sets has_title=1.0 for markdown headings."""
        text = "# Main Title\n\nSome content here.\n\n## Subtitle\n\nMore content."
        features = extract_features(text)

        assert features["has_title"] == 1.0


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

    def test_ad_keyword_branch(self):
        """classify_fast hits ad_keyword_count >= 3 branch (score=30)."""
        # 3+ ad keywords, fewer than 2 scam keywords
        text = "推荐码ABCD，优惠券可以在这里领取，折扣很大，关注公众号了解更多。这是正常内容补充字数避免过短。"
        result = classify_fast(text)

        assert result.predicted_score == 30.0
        assert result.confidence == 0.8
        assert result.category == "low"

    def test_emotional_pattern_branch(self):
        """classify_fast hits emotional_pattern_count >= 3 branch (score=35)."""
        # 3+ emotional patterns, fewer than 2 scam keywords, fewer than 3 ad keywords
        text = "震惊!!!必看!!!不转不是中国人!!!这条消息你一定要知道，太重要了。补充内容避免过短。"
        result = classify_fast(text)

        assert result.predicted_score == 35.0
        assert result.confidence == 0.75
        assert result.category == "low"

    def test_ai_pattern_branch(self):
        """classify_fast hits ai_pattern_count >= 3 branch (score=45)."""
        # 3+ AI patterns, no scam/ad/emotional triggers in sufficient quantity
        text = (
            "综上所述，本文探讨了人工智能发展的多个方面。"
            "总而言之，技术进步为社会带来了深远影响。"
            "值得注意的是，我们需要关注伦理问题。"
            "需要指出的是，未来发展还有很多不确定性。"
            "这段文字需要足够长以避免触发短文本分支。" * 3
        )
        result = classify_fast(text)

        assert result.predicted_score == 45.0
        assert result.confidence == 0.6
        assert result.category == "low"

    def test_high_quality_content_branch(self):
        """classify_fast hits high-quality branch (score=70) for long structured content."""
        # char_count > 2000, paragraph_count > 5, no scam/ad keywords
        paragraphs = [
            f"这是第{i}段有意义的内容。" + "人工智能技术正在快速发展，对各行各业产生深远影响。" * 10
            for i in range(8)
        ]
        text = "\n\n".join(paragraphs)
        assert len(text) > 2000

        result = classify_fast(text)

        assert result.predicted_score == 70.0
        assert result.confidence == 0.6
        assert result.category == "good"

    def test_custom_confidence_threshold_skip_llm(self):
        """classify_fast with low confidence_threshold marks should_skip_llm=True."""
        # Use scam content which gets confidence=0.9 (>= 0.5 threshold)
        text = "日入过万！躺赚！限时免费！私聊领取！"
        result = classify_fast(text, confidence_threshold=0.5)

        assert result.confidence >= 0.5
        assert result.should_skip_llm is True

    def test_scam_keyword_count_two_branch(self):
        """classify_fast hits scam_keyword_count >= 2 branch (score=25)."""
        # Exactly 2 scam keywords, no other high triggers
        text = "日入过万的副业机会，了解一下详情。这段文字需要足够长不触发短文本。" * 2
        result = classify_fast(text)

        assert result.predicted_score == 25.0
        assert result.confidence == 0.8
        assert result.category == "junk"

    @patch("src.core.fast_classifier._try_ml_model")
    def test_classify_fast_uses_ml_model_when_available(self, mock_ml):
        """classify_fast returns ML model result when available."""
        features = extract_features("test content")
        mock_result = ClassifierResult(
            predicted_score=80,
            confidence=0.92,
            category="good",
            should_skip_llm=True,
            features=features,
        )
        mock_ml.return_value = mock_result

        result = classify_fast("test content")

        assert result.predicted_score == 80
        assert result.category == "good"
        assert result.should_skip_llm is True


class TestTryMlModel:
    """Tests for _try_ml_model."""

    @pytest.fixture(autouse=True)
    def reset_loaded_model(self):
        """Reset the global _loaded_model after each test to prevent cross-test contamination."""
        yield
        import src.core.fast_classifier
        src.core.fast_classifier._loaded_model = None

    def test_returns_none_when_model_file_missing(self):
        """_try_ml_model returns None when no model file exists."""
        features = extract_features("Some normal text for testing.")
        result = _try_ml_model(features)

        assert result is None

    @patch("src.core.fast_classifier._MODEL_PATH")
    @patch("src.core.fast_classifier._loaded_model", None)
    def test_returns_result_when_model_exists(self, mock_path):
        """_try_ml_model returns ClassifierResult when model file is available."""
        from unittest.mock import MagicMock
        import sys

        mock_path.exists.return_value = True

        # Mock numpy module since it may not be installed
        mock_np = MagicMock()
        mock_np.array = lambda x: x

        # Create a mock model
        mock_model = MagicMock()
        mock_model.predict.return_value = ["good"]
        mock_model.predict_proba.return_value = [[0.02, 0.02, 0.04, 0.92]]

        features = extract_features("Some normal text for testing the model.")

        with patch.dict(sys.modules, {"numpy": mock_np}), \
             patch("builtins.open"), \
             patch("pickle.load", return_value=mock_model):
            result = _try_ml_model(features)

        assert result is not None
        assert isinstance(result, ClassifierResult)
        assert result.predicted_score == 80
        assert result.category == "good"
        assert result.confidence >= 0.9
        assert result.should_skip_llm is True

    @patch("src.core.fast_classifier._MODEL_PATH")
    @patch("src.core.fast_classifier._loaded_model", None)
    def test_returns_none_on_exception(self, mock_path):
        """_try_ml_model returns None when model loading fails."""
        mock_path.exists.return_value = True

        features = extract_features("Some text.")

        with patch("builtins.open", side_effect=OSError("file corrupted")):
            result = _try_ml_model(features)

        assert result is None

    @patch("src.core.fast_classifier._MODEL_PATH")
    @patch("src.core.fast_classifier._loaded_model", None)
    def test_uses_cached_model_on_second_call(self, mock_path):
        """_try_ml_model uses the cached model on subsequent calls without reloading."""
        from unittest.mock import MagicMock, call
        import sys

        mock_path.exists.return_value = True

        # Mock numpy module
        mock_np = MagicMock()
        mock_np.array = lambda x: x

        mock_model = MagicMock()
        mock_model.predict.return_value = ["low"]
        mock_model.predict_proba.return_value = [[0.1, 0.7, 0.1, 0.1]]

        features = extract_features("Some text for testing cached model path.")

        # First call loads the model via pickle.load
        with patch.dict(sys.modules, {"numpy": mock_np}), \
             patch("builtins.open"), \
             patch("pickle.load", return_value=mock_model) as mock_pickle_load:
            result1 = _try_ml_model(features)
            assert mock_pickle_load.call_count == 1

        assert result1 is not None
        assert result1.category == "low"

        # Reset global to simulate a fresh state, then set it to our cached model
        # to validate that _try_ml_model skips pickle.load when _loaded_model is set
        import src.core.fast_classifier
        src.core.fast_classifier._loaded_model = mock_model

        # Second call should use the cached global and NOT call pickle.load
        with patch.dict(sys.modules, {"numpy": mock_np}), \
             patch("pickle.load") as mock_pickle_load_2:
            result2 = _try_ml_model(features)
            # pickle.load must NOT be called -- the model is already cached
            mock_pickle_load_2.assert_not_called()

        assert result2 is not None
        assert result2.category == "low"
