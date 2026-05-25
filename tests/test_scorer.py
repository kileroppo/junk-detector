"""Tests for the main scoring orchestrator (src.core.scorer).

Verifies the score() function coordinates rules, content filter,
and LLM judge correctly. All LLM calls are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scorer import _calculate_overall, _generate_labels, score
from src.models.score import DimensionScores, ScoreResult, ScoringConfig


def _make_llm_response_content(dimensions: dict | None = None) -> str:
    """Build a JSON string like what litellm returns from the LLM."""
    data = {
        "originality": 75,
        "info_density": 60,
        "reasoning_quality": 70,
        "readability": 80,
        "timeliness": 50,
        "ai_generated_prob": 20,
        "emotional_manipulation": 10,
        "advertorial_prob": 15,
        "scam_prob": 5,
        "summary": "Test content evaluation",
        "confidence": 0.85,
        "labels": [],
    }
    if dimensions:
        data.update(dimensions)
    return json.dumps(data)


def _make_mock_litellm_response(content: str, cost: float = 0.001):
    """Create a mock object matching litellm.acompletion() return shape."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response._hidden_params = {"response_cost": cost}
    return mock_response


class TestScoreOrchestration:
    """Tests verifying the scoring orchestrator behavior."""

    @patch("src.core.scorer.judge")
    @patch("src.core.content_filter.check_content")
    async def test_content_filter_rejection_returns_score_zero(
        self, mock_filter, mock_judge
    ):
        """When content filter rejects content, score is 0 and LLM is not called."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(
            passed=False,
            violation_type="赌博",
            violation_details="detected gambling content",
            matched_patterns=["网上赌场", "在线博彩"],
        )
        result = await score("网上赌场在线博彩赌球")
        assert result.overall_score == 0.0
        assert result.model_used == "content_filter"
        mock_judge.assert_not_called()

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_llm_called_when_rules_dont_cover_all_dimensions(
        self, mock_filter, mock_acompletion
    ):
        """LLM judge is invoked when rules cannot cover all 9 dimensions."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        result = await score("A normal article about technology trends.")
        assert mock_acompletion.called
        assert result.model_used != "rules_only"

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_fallback_model_triggered_on_low_confidence(
        self, mock_filter, mock_acompletion
    ):
        """When primary model returns low confidence, fallback model is called."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # Primary model returns low confidence, fallback returns high
        low_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.3}), cost=0.001
        )
        high_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.9}), cost=0.002
        )
        mock_acompletion.side_effect = [low_conf_response, high_conf_response]

        config = ScoringConfig(
            primary_model="test/primary",
            fallback_model="test/fallback",
            confidence_threshold=0.7,
        )
        result = await score("Some text to analyze", config=config)
        # Should have been called twice (primary + fallback)
        assert mock_acompletion.call_count == 2

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_cost_accumulation_after_fallback(
        self, mock_filter, mock_acompletion
    ):
        """Total cost includes both primary and fallback model calls."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        primary_cost = 0.005
        fallback_cost = 0.010
        low_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.3}), cost=primary_cost
        )
        high_conf_response = _make_mock_litellm_response(
            _make_llm_response_content({"confidence": 0.9}), cost=fallback_cost
        )
        mock_acompletion.side_effect = [low_conf_response, high_conf_response]

        config = ScoringConfig(
            primary_model="test/primary",
            fallback_model="test/fallback",
            confidence_threshold=0.7,
        )
        result = await score("Cost test content", config=config)
        assert result.cost == pytest.approx(primary_cost + fallback_cost, abs=0.001)

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_rules_only_path_skips_llm(self, mock_filter, mock_acompletion):
        """When rules cover all 9 dimensions with high confidence, LLM is skipped."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # Patch apply_rules to cover ALL dimensions
        all_dims = [
            "originality", "info_density", "reasoning_quality", "readability",
            "timeliness", "ai_generated_prob", "emotional_manipulation",
            "advertorial_prob", "scam_prob",
        ]
        from src.core.rules import RuleResult

        mock_rule_result = RuleResult(
            matched_rules=["test_rule"],
            dimension_overrides={dim: 50.0 for dim in all_dims},
            confidence={dim: 0.95 for dim in all_dims},
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            result = await score("Any text")

        assert result.model_used == "rules_only"
        assert result.cost == 0.0
        mock_acompletion.assert_not_called()

    def test_calculate_overall_with_default_weights(self):
        """Overall score calculation produces a value in [0, 100]."""
        dimensions = DimensionScores(
            originality=80,
            info_density=70,
            reasoning_quality=75,
            readability=85,
            timeliness=60,
            ai_generated_prob=20,
            emotional_manipulation=10,
            advertorial_prob=15,
            scam_prob=5,
        )
        config = ScoringConfig()
        overall = _calculate_overall(dimensions, config)
        assert 0 <= overall <= 100

    def test_generate_labels_from_high_scores(self):
        """Labels are generated when dimension scores exceed thresholds."""
        dimensions = DimensionScores(
            originality=85,
            info_density=85,
            reasoning_quality=75,
            readability=80,
            timeliness=50,
            ai_generated_prob=80,
            emotional_manipulation=70,
            advertorial_prob=75,
            scam_prob=65,
        )
        config = ScoringConfig()
        labels = _generate_labels(dimensions, config)
        assert "高质量原创" in labels
        assert "信息密度高" in labels
        assert "可能AI生成" in labels
        assert "情绪操纵" in labels
        assert "疑似软文" in labels
        assert "疑似骗局" in labels

    @patch("src.core.scorer.judge")
    @patch("src.core.content_filter.check_content")
    async def test_cache_hit_returns_cached_result(self, mock_filter, mock_judge):
        """When DB has a cached result within 7 days, it is returned without LLM call."""
        from src.core.content_filter import FilterResult
        from datetime import datetime, timezone

        mock_filter.return_value = FilterResult(passed=True)

        cached_record = {
            "overall_score": 65.0,
            "dimensions": {
                "originality": 70, "info_density": 60, "reasoning_quality": 65,
                "readability": 75, "timeliness": 50, "ai_generated_prob": 15,
                "emotional_manipulation": 10, "advertorial_prob": 20, "scam_prob": 5,
            },
            "labels": ["高质量原创"],
            "summary": "Cached summary",
            "confidence": 0.9,
            "model_used": "deepseek/deepseek-chat",
            "rule_hits": [],
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

        with patch("src.storage.db.query_by_content_hash", return_value=cached_record):
            result = await score("Some cached content text")

        assert result.model_used == "cache"
        assert result.cost == 0.0
        assert result.overall_score == 65.0
        mock_judge.assert_not_called()

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_output_validation_rejects_too_perfect_positive(
        self, mock_filter, mock_acompletion
    ):
        """Suspicious all-positive LLM output is rejected with neutral dimensions."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # All positive maxed, all negative zeroed
        suspicious_dims = {
            "originality": 100, "info_density": 100, "reasoning_quality": 100,
            "readability": 100, "timeliness": 100, "ai_generated_prob": 0,
            "emotional_manipulation": 0, "advertorial_prob": 0, "scam_prob": 0,
            "confidence": 0.99,
        }
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content(suspicious_dims)
        )

        result = await score("Injected content that tricks LLM")
        assert result.model_used == "validation_rejected"
        assert result.confidence == 0.1
        assert result.overall_score == 50.0
        # Dimensions should be neutral (all 50)
        assert result.dimensions.originality == 50
        assert result.dimensions.scam_prob == 50

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_output_validation_rejects_too_perfect_negative(
        self, mock_filter, mock_acompletion
    ):
        """Suspicious all-negative LLM output is also rejected."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # Inverse pattern: all positive zeroed, all negative maxed
        suspicious_dims = {
            "originality": 0, "info_density": 1, "reasoning_quality": 0,
            "readability": 2, "timeliness": 0, "ai_generated_prob": 100,
            "emotional_manipulation": 99, "advertorial_prob": 100, "scam_prob": 98,
            "confidence": 0.95,
        }
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content(suspicious_dims)
        )

        result = await score("Content designed to look maximally bad")
        assert result.model_used == "validation_rejected"
        assert result.confidence == 0.1
        assert result.dimensions.originality == 50
        assert result.dimensions.scam_prob == 50

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_cache_stale_result_triggers_llm(
        self, mock_filter, mock_acompletion
    ):
        """Cached result with scored_at > 7 days old should still call LLM."""
        from datetime import datetime, timedelta, timezone
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        # Cache record with scored_at 8 days ago (stale)
        stale_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        cached_record = {
            "overall_score": 65.0,
            "dimensions": {
                "originality": 70, "info_density": 60, "reasoning_quality": 65,
                "readability": 75, "timeliness": 50, "ai_generated_prob": 15,
                "emotional_manipulation": 10, "advertorial_prob": 20, "scam_prob": 5,
            },
            "labels": [],
            "summary": "Stale cached summary",
            "confidence": 0.9,
            "model_used": "deepseek/deepseek-chat",
            "rule_hits": [],
            "scored_at": stale_time,
        }

        with patch("src.storage.db.query_by_content_hash", return_value=cached_record):
            result = await score("Some content that has a stale cache entry")

        # LLM should be called since cache is stale
        assert mock_acompletion.called
        assert result.model_used != "cache"

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_cache_no_timezone_info(self, mock_filter, mock_acompletion):
        """Cached result with naive datetime (no timezone) should still work as cache hit."""
        from datetime import datetime, timedelta, timezone
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        # Recent naive datetime (no +00:00 suffix) - should be treated as UTC
        recent_naive = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        cached_record = {
            "overall_score": 72.0,
            "dimensions": {
                "originality": 75, "info_density": 65, "reasoning_quality": 70,
                "readability": 80, "timeliness": 55, "ai_generated_prob": 10,
                "emotional_manipulation": 5, "advertorial_prob": 15, "scam_prob": 3,
            },
            "labels": ["高质量原创"],
            "summary": "Naive datetime cached summary",
            "confidence": 0.88,
            "model_used": "deepseek/deepseek-chat",
            "rule_hits": [],
            "scored_at": recent_naive,
        }

        with patch("src.storage.db.query_by_content_hash", return_value=cached_record):
            result = await score("Content with naive datetime cache entry")

        # Should use cache since scored_at is recent (after adding UTC tz)
        assert result.model_used == "cache"
        assert result.cost == 0.0
        mock_acompletion.assert_not_called()

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_cache_lookup_exception(self, mock_filter, mock_acompletion):
        """When cache lookup raises an exception, scorer continues to LLM."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        with patch(
            "src.storage.db.query_by_content_hash",
            side_effect=Exception("DB connection failed"),
        ):
            result = await score("Content when cache DB is down")

        # Should still produce a result via LLM
        assert mock_acompletion.called
        assert result.model_used != "cache"

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_fast_classifier_logs_skip_recommendation(
        self, mock_filter, mock_acompletion
    ):
        """When fast_classifier recommends skipping LLM, scorer still calls LLM (TODO path)."""
        from src.core.content_filter import FilterResult
        from src.core.fast_classifier import ClassifierResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        mock_classifier_result = ClassifierResult(
            predicted_score=15.0,
            confidence=0.95,
            category="junk",
            should_skip_llm=True,
            features={"char_count": 100},
        )

        with patch(
            "src.core.fast_classifier.classify_fast",
            return_value=mock_classifier_result,
        ):
            result = await score("Content that classifier thinks is junk")

        # LLM should still be called (the TODO says log and continue)
        assert mock_acompletion.called

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_fast_classifier_unavailable(self, mock_filter, mock_acompletion):
        """When fast_classifier raises an exception, scorer continues normally."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        with patch(
            "src.core.fast_classifier.classify_fast",
            side_effect=Exception("classifier not available"),
        ):
            result = await score("Content when classifier is broken")

        # Should still produce a result via LLM
        assert mock_acompletion.called
        assert result.model_used != ""

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_platform_detection_with_source_url(
        self, mock_filter, mock_acompletion
    ):
        """Passing source_url matching a known platform applies platform weights."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        result = await score(
            "一篇关于技术趋势的公众号文章内容",
            source_url="https://mp.weixin.qq.com/s/some-article-id",
        )

        # Should complete successfully with platform weights applied
        assert mock_acompletion.called
        assert 0 <= result.overall_score <= 100

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_platform_extra_rules_boost_advertorial(
        self, mock_filter, mock_acompletion
    ):
        """Platform extra rules matching keywords boost advertorial_prob and appear in rule_hits."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content()
        )

        # Content containing wechat platform extra rules keywords
        content = "这是一篇好文章，关注公众号获取更多内容，点击原文查看详情"
        result = await score(
            content,
            source_url="https://mp.weixin.qq.com/s/some-article",
        )

        # Platform rule hits should be recorded
        platform_hits = [h for h in result.rule_hits if "platform_wechat:" in h]
        assert len(platform_hits) >= 2  # "关注公众号" and "点击原文" matched

    def test_generate_labels_skips_unknown_threshold(self):
        """Labels with no configured threshold are skipped (threshold is None)."""
        dimensions = DimensionScores(
            originality=90,
            info_density=90,
            reasoning_quality=75,
            readability=80,
            timeliness=50,
            ai_generated_prob=10,
            emotional_manipulation=10,
            advertorial_prob=10,
            scam_prob=5,
        )
        # Config with a missing threshold (remove one from defaults)
        config = ScoringConfig(
            label_thresholds={
                "高质量原创": 80.0,
                "信息密度高": 80.0,
                # "可能AI生成" not in thresholds -> threshold is None -> continue
            }
        )
        labels = _generate_labels(dimensions, config)
        assert "高质量原创" in labels
        assert "信息密度高" in labels
        # "可能AI生成" not in thresholds, so even if score were high it won't appear
        assert "可能AI生成" not in labels

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_output_validation_rejects_all_100(
        self, mock_filter, mock_acompletion
    ):
        """All dimensions at exactly 100 triggers suspicious output rejection."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        all_100_dims = {
            "originality": 100, "info_density": 100, "reasoning_quality": 100,
            "readability": 100, "timeliness": 100, "ai_generated_prob": 100,
            "emotional_manipulation": 100, "advertorial_prob": 100, "scam_prob": 100,
            "confidence": 0.99,
        }
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content(all_100_dims)
        )

        result = await score("All dimensions maxed out")
        assert result.model_used == "validation_rejected"
        assert result.confidence == 0.1

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_output_validation_rejects_all_zero(
        self, mock_filter, mock_acompletion
    ):
        """All dimensions at exactly 0 triggers suspicious output rejection."""
        from src.core.content_filter import FilterResult

        mock_filter.return_value = FilterResult(passed=True)

        all_zero_dims = {
            "originality": 0, "info_density": 0, "reasoning_quality": 0,
            "readability": 0, "timeliness": 0, "ai_generated_prob": 0,
            "emotional_manipulation": 0, "advertorial_prob": 0, "scam_prob": 0,
            "confidence": 0.99,
        }
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content(all_zero_dims)
        )

        result = await score("All dimensions zeroed out")
        assert result.model_used == "validation_rejected"
        assert result.confidence == 0.1

    @patch("src.core.llm_judge.litellm.acompletion")
    @patch("src.core.content_filter.check_content")
    async def test_rule_overrides_applied_to_llm_result(
        self, mock_filter, mock_acompletion
    ):
        """High-confidence rule overrides are applied on top of LLM dimensions."""
        from src.core.content_filter import FilterResult
        from src.core.rules import RuleResult

        mock_filter.return_value = FilterResult(passed=True)
        mock_acompletion.return_value = _make_mock_litellm_response(
            _make_llm_response_content({"scam_prob": 10, "confidence": 0.85})
        )

        # Mock rules to override scam_prob with high confidence
        mock_rule_result = RuleResult(
            matched_rules=["scam_keyword_detected"],
            dimension_overrides={"scam_prob": 90.0},
            confidence={"scam_prob": 0.95},
        )

        with patch("src.core.scorer.apply_rules", return_value=mock_rule_result):
            result = await score("Content with scam keywords detected by rules")

        # The rule override should have set scam_prob to 90
        assert result.dimensions.scam_prob == 90.0
        assert result.dimension_sources.get("scam_prob") == "rule"
        assert "scam_keyword_detected" in result.rule_hits
