"""Tests for content type classifier."""

from __future__ import annotations

import pytest

from src.core.content_classifier import (
    ClassificationResult,
    ContentType,
    TYPE_LABELS_ZH,
    WEIGHT_ADJUSTMENTS,
    classify_content,
)


class TestToolListDetection:
    """Test detection of tool list / resource compilation articles."""

    def test_detects_tool_list_with_keywords(self):
        text = """
        2024年最好用的AI工具合集推荐！TOP 10 神器盘点清单
        1. ChatGPT - https://chat.openai.com
        2. Claude - https://claude.ai
        3. Midjourney - https://midjourney.com
        4. Stable Diffusion - https://stability.ai
        5. Notion AI - https://notion.so
        这些工具都是我们精心整理的资源汇总。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.TOOL_LIST
        assert result.confidence > 0
        assert result.type_label_zh == TYPE_LABELS_ZH[ContentType.TOOL_LIST]

    def test_tool_list_has_correct_weight_adjustments(self):
        text = "2024年推荐工具合集盘点清单TOP 10必备神器利器资源汇总整理"
        result = classify_content(text)
        assert result.primary_type == ContentType.TOOL_LIST
        assert result.weight_adjustments == WEIGHT_ADJUSTMENTS[ContentType.TOOL_LIST]
        assert result.weight_adjustments["originality"] == 0.5
        assert result.weight_adjustments["info_density"] == 1.5

    def test_tool_list_with_bullet_points_and_urls(self):
        text = """推荐工具合集:
- 工具A https://tool-a.com
- 工具B https://tool-b.com
- 工具C https://tool-c.com
- 工具D https://tool-d.com
- 工具E https://tool-e.com
- 工具F https://tool-f.com
"""
        result = classify_content(text)
        assert result.primary_type == ContentType.TOOL_LIST


class TestTutorialDetection:
    """Test detection of tutorial / how-to articles."""

    def test_detects_tutorial_with_keywords(self):
        text = """
        如何用Python写爬虫 - 教程

        第一步：安装依赖
        ```python
        pip install requests beautifulsoup4
        ```

        第二步：写代码
        ```python
        import requests
        ```

        第三步：运行
        步骤很简单，手把手教你从零开始入门。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.TUTORIAL
        assert result.confidence > 0
        assert "readability" in result.weight_adjustments

    def test_tutorial_with_code_blocks(self):
        text = """教程：如何部署
        步骤一：
        ```
        docker build -t app .
        ```
        步骤二：
        ```
        docker run -p 8080:8080 app
        ```
        步骤三：
        ```
        curl localhost:8080
        ```
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.TUTORIAL


class TestOpinionDetection:
    """Test detection of opinion / commentary articles."""

    def test_detects_opinion_with_first_person(self):
        text = """
        我认为现在的AI发展太快了。我觉得这个观点很多人会同意。
        在我看来，依我看，这不是一个简单的技术问题，而是一个社会问题。
        我的看法是，不得不说，个人认为我们需要更多的讨论。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.OPINION
        assert result.weight_adjustments["reasoning_quality"] == 1.5

    def test_opinion_boosts_reasoning_quality(self):
        text = "我认为我觉得观点看法个人认为我的理解依我看在我看来不得不说"
        result = classify_content(text)
        assert result.primary_type == ContentType.OPINION
        assert result.weight_adjustments.get("reasoning_quality") == 1.5


class TestNewsDetection:
    """Test detection of news articles."""

    def test_detects_news_with_keywords(self):
        text = """
        新华社北京12月1日电 据记者报道，官方今日发布公告。
        据悉，这是一则重要消息。据了解，发布会将于下周举行。
        央视新闻通报了最新进展。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.NEWS
        assert result.weight_adjustments["timeliness"] == 1.5


class TestAdvertorialDetection:
    """Test detection of advertorial / promotional content."""

    def test_detects_advertorial_with_keywords(self):
        text = """
        推荐码：ABC123，用这个邀请码可以获得优惠折扣！
        限时返利活动，立减50元！快来下单吧！
        购买链接在这里，领券享受佣金返现。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.ADVERTORIAL
        assert result.weight_adjustments["advertorial_prob"] == -2.0
        assert result.weight_adjustments["scam_prob"] == -1.5


class TestPersonalStoryDetection:
    """Test detection of personal story / experience articles."""

    def test_detects_personal_story(self):
        text = """
        我的经历分享：那年我第一次创业的心路历程。
        记得那时候，我还是个刚毕业的学生。亲身经历过才知道创业不易。
        回忆起来，那段感悟至今难忘。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.PERSONAL_STORY
        assert result.weight_adjustments["originality"] == 1.3


class TestAcademicDetection:
    """Test detection of academic / research articles."""

    def test_detects_academic_with_keywords(self):
        text = """
        研究表明，数据显示在这个实验中，样本量为500个。
        方法论采用了双盲实验设计。文献引用了前人的论文。
        统计分析表明结果具有显著性差异。假设得到了验证。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.ACADEMIC
        assert result.weight_adjustments["reasoning_quality"] == 1.5
        assert result.weight_adjustments["info_density"] == 1.5


class TestAIGeneratedDetection:
    """Test detection of AI-generated content."""

    def test_detects_ai_generated_with_formulaic_transitions(self):
        text = """
        总而言之，这是一个重要的话题。综上所述，我们可以得出结论。
        总的来说，情况并不乐观。值得注意的是，这个问题很复杂。
        不可否认，我们面临挑战。毋庸置疑，改变是必要的。
        """
        result = classify_content(text)
        assert result.primary_type == ContentType.AI_GENERATED
        assert result.weight_adjustments["ai_generated_prob"] == -1.5
        assert result.weight_adjustments["originality"] == 0.3


class TestUnknownAndEdgeCases:
    """Test handling of unknown, ambiguous, or edge-case content."""

    def test_empty_text_returns_unknown(self):
        result = classify_content("")
        assert result.primary_type == ContentType.UNKNOWN
        assert result.confidence == 0.0
        assert result.weight_adjustments == {}

    def test_whitespace_only_returns_unknown(self):
        result = classify_content("   \n\t  ")
        assert result.primary_type == ContentType.UNKNOWN
        assert result.confidence == 0.0

    def test_short_generic_text_returns_unknown(self):
        text = "今天天气不错。"
        result = classify_content(text)
        assert result.primary_type == ContentType.UNKNOWN

    def test_result_always_has_type_label(self):
        result = classify_content("一些普通文字")
        assert result.type_label_zh != ""

    def test_type_probabilities_are_populated(self):
        text = "推荐工具合集盘点"
        result = classify_content(text)
        assert len(result.type_probabilities) > 0
        # All probabilities should be between 0 and 1
        for prob in result.type_probabilities.values():
            assert 0 <= prob <= 1

    def test_confidence_between_zero_and_one(self):
        text = "这是一篇关于如何使用工具的教程推荐"
        result = classify_content(text)
        assert 0 <= result.confidence <= 1

    def test_classification_result_structure(self):
        text = "推荐工具合集"
        result = classify_content(text)
        assert isinstance(result, ClassificationResult)
        assert isinstance(result.primary_type, ContentType)
        assert isinstance(result.confidence, float)
        assert isinstance(result.type_probabilities, dict)
        assert isinstance(result.weight_adjustments, dict)
        assert isinstance(result.type_label_zh, str)


class TestWeightAdjustments:
    """Test weight adjustment calculation correctness."""

    def test_all_content_types_have_weight_adjustments(self):
        """Every ContentType should have an entry in WEIGHT_ADJUSTMENTS."""
        for ct in ContentType:
            assert ct in WEIGHT_ADJUSTMENTS

    def test_unknown_has_empty_adjustments(self):
        assert WEIGHT_ADJUSTMENTS[ContentType.UNKNOWN] == {}

    def test_weight_adjustments_are_dicts(self):
        for ct, adjustments in WEIGHT_ADJUSTMENTS.items():
            assert isinstance(adjustments, dict)
            for key, value in adjustments.items():
                assert isinstance(key, str)
                assert isinstance(value, (int, float))

    def test_type_labels_complete(self):
        """Every ContentType should have a Chinese label."""
        for ct in ContentType:
            assert ct in TYPE_LABELS_ZH
            assert len(TYPE_LABELS_ZH[ct]) > 0


class TestScorerIntegration:
    """Test content classifier integration with scorer (mock LLM)."""

    @pytest.mark.asyncio
    async def test_scorer_applies_weight_adjustments(self, mock_config):
        """Verify that scorer applies content classification weight adjustments."""
        from unittest.mock import AsyncMock, patch

        from src.models.score import DimensionScores, ScoreResult

        mock_result = ScoreResult(
            overall_score=65.0,
            dimensions=DimensionScores(
                originality=70,
                info_density=60,
                reasoning_quality=65,
                readability=75,
                timeliness=50,
                ai_generated_prob=20,
                emotional_manipulation=15,
                advertorial_prob=10,
                scam_prob=5,
            ),
            labels=[],
            summary="Test",
            confidence=0.9,
            model_used="test",
        )

        # Tutorial text
        tutorial_text = "如何用Python写爬虫教程 第一步步骤 手把手入门 从零开始"

        with (
            patch("src.core.scorer.judge", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.scorer.smart_truncate", return_value=tutorial_text),
            patch("src.storage.db.get_cached_score", return_value=None),
            patch("src.core.fast_classifier.classify_fast") as mock_fast,
        ):
            mock_fast.side_effect = Exception("not available")

            from src.core.scorer import score

            result = await score(tutorial_text, config=mock_config)
            # The result should have content_type set
            assert result.content_type == "tutorial"
            assert result.content_type_label == "教程/操作指南"

    @pytest.mark.asyncio
    async def test_scorer_handles_unknown_type_gracefully(self, mock_config):
        """If content type is unknown, no weight adjustments are applied."""
        from unittest.mock import AsyncMock, patch

        from src.models.score import DimensionScores, ScoreResult

        mock_result = ScoreResult(
            overall_score=65.0,
            dimensions=DimensionScores(
                originality=70,
                info_density=60,
                reasoning_quality=65,
                readability=75,
                timeliness=50,
                ai_generated_prob=20,
                emotional_manipulation=15,
                advertorial_prob=10,
                scam_prob=5,
            ),
            labels=[],
            summary="Test",
            confidence=0.9,
            model_used="test",
        )

        # Generic text with no clear type
        generic_text = "今天天气不错。"

        with (
            patch("src.core.scorer.judge", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.scorer.smart_truncate", return_value=generic_text),
            patch("src.storage.db.get_cached_score", return_value=None),
            patch("src.core.fast_classifier.classify_fast") as mock_fast,
        ):
            mock_fast.side_effect = Exception("not available")

            from src.core.scorer import score

            result = await score(generic_text, config=mock_config)
            # content_type should be None for unknown
            assert result.content_type is None
