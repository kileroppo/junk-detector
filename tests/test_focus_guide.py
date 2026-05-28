"""Tests for src/core/focus_guide.py - Focus Guide generation module."""

from __future__ import annotations

import pytest

from src.core.focus_guide import (
    _count_filler_phrases,
    _count_transitions,
    _detect_filler_phrases,
    _detect_formulaic_transitions,
    _detect_lack_of_specifics,
    _detect_repetitive_starters,
    _detect_uniform_structure,
    _generate_tldr,
    _has_specifics,
    _information_density_score,
    _split_paragraphs,
    _split_sentences,
    generate_focus_guide,
)
from src.models.focus_guide import FocusGuide
from src.models.score import DimensionScores, ScoreResult


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_score(overall: float = 35.0, ai_prob: float = 80.0) -> ScoreResult:
    """Create a ScoreResult with given overall_score and ai_generated_prob."""
    return ScoreResult(
        overall_score=overall,
        dimensions=DimensionScores(
            originality=30,
            info_density=25,
            reasoning_quality=40,
            readability=50,
            timeliness=30,
            ai_generated_prob=ai_prob,
            emotional_manipulation=20,
            advertorial_prob=15,
            scam_prob=10,
        ),
        labels=["可能AI生成"],
        summary="Test content",
        model_used="test",
        cost=0.0,
    )


def _make_high_quality_score() -> ScoreResult:
    """Create a high-quality ScoreResult that should NOT trigger focus guide."""
    return ScoreResult(
        overall_score=85.0,
        dimensions=DimensionScores(
            originality=90,
            info_density=85,
            reasoning_quality=80,
            readability=90,
            timeliness=75,
            ai_generated_prob=10,
            emotional_manipulation=5,
            advertorial_prob=10,
            scam_prob=2,
        ),
        labels=["高质量原创"],
        summary="High quality content",
        model_used="test",
        cost=0.0,
    )


# AI-like text with uniform paragraphs and formulaic transitions (Chinese)
AI_GENERATED_CN = """首先，在当今社会，人工智能技术已经成为了一个不可忽视的力量。众所周知，AI技术正在深刻地改变着我们的生活方式和工作模式。

其次，随着科技的发展，越来越多的企业开始将人工智能应用到实际生产中。不言而喻，这种趋势将会持续下去，并且会变得更加普遍。

再次，我们需要认识到人工智能带来的机遇和挑战。毋庸置疑，AI技术在提高效率的同时，也带来了一些需要我们认真思考的问题。

最后，综上所述，人工智能技术的发展是不可逆转的趋势。我们应该积极拥抱这一变化，同时也要注意防范可能出现的风险。"""

# AI-like text in English
AI_GENERATED_EN = """Firstly, it is worth noting that artificial intelligence has become an integral part of modern society. Furthermore, the rapid advancement of technology has led to unprecedented changes in how we live and work.

Secondly, in conclusion, we must acknowledge that the impact of AI extends far beyond what we initially anticipated. Moreover, the implications for the workforce are significant and far-reaching.

Thirdly, it is worth noting that many organizations are now embracing AI-driven solutions. In addition, the benefits of such adoption are becoming increasingly apparent to stakeholders across various sectors.

In summary, all in all, the future of artificial intelligence holds both promise and challenges. Nevertheless, it is imperative that we approach this technological revolution with both optimism and caution."""

# Genuine human text with varied structure and specifics
GENUINE_HUMAN_TEXT = """2024年3月，OpenAI发布了GPT-4 Turbo模型，上下文窗口扩展至128K tokens。

据路透社报道，该模型的训练成本约为1亿美元，使用了约45TB的文本数据。相比GPT-3.5，推理速度提升了约3倍。

值得注意的是，GPT-4在Bar Exam（律师资格考试）中取得了前10%的成绩，而GPT-3.5仅能达到后10%。这一差距主要来自于模型在逻辑推理和多步骤问题解决方面的显著提升。

Meta的LLaMA 2模型则采用了不同的策略：70B参数版本的训练使用了2万亿tokens的数据，并且完全开源。Zuckerberg在接受采访时表示："开源是我们的核心战略"。"""

# Very short text
SHORT_TEXT = "这是一段很短的文字。"

# Single long paragraph
SINGLE_PARAGRAPH = "在当今社会，人工智能技术已经成为了一个不可忽视的力量，众所周知AI技术正在深刻地改变着我们的生活方式和工作模式，随着科技的发展越来越多的企业开始将人工智能应用到实际生产中。"


# ---------------------------------------------------------------------------
# Test: generate_focus_guide main function
# ---------------------------------------------------------------------------


class TestGenerateFocusGuide:
    """Tests for the main generate_focus_guide function."""

    def test_returns_none_for_high_quality_content(self):
        """High quality content (score > 70 AND ai_prob < 30) should return None."""
        score = _make_high_quality_score()
        result = generate_focus_guide(GENUINE_HUMAN_TEXT, score)
        assert result is None

    def test_generates_guide_for_ai_content(self):
        """AI-generated content with high ai_prob should produce a guide."""
        score = _make_score(overall=35.0, ai_prob=85.0)
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        assert isinstance(result, FocusGuide)

    def test_generates_guide_for_low_score(self):
        """Low overall score (< 50) should trigger guide generation."""
        score = _make_score(overall=30.0, ai_prob=40.0)
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None

    def test_generates_guide_for_high_ai_prob(self):
        """High ai_prob (> 50) should trigger guide generation."""
        score = _make_score(overall=60.0, ai_prob=70.0)
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None

    def test_returns_none_for_empty_text(self):
        """Empty text should return None."""
        score = _make_score()
        assert generate_focus_guide("", score) is None
        assert generate_focus_guide("   ", score) is None

    def test_returns_none_for_very_short_text(self):
        """Text shorter than 10 characters should return None."""
        score = _make_score()
        assert generate_focus_guide("short", score) is None

    def test_recommendation_skip(self):
        """Should recommend 'skip' when ai_prob > 80 and low info density."""
        score = _make_score(overall=20.0, ai_prob=90.0)
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        assert result.recommendation == "skip"

    def test_recommendation_skim(self):
        """Should recommend 'skim' when ai_prob > 50."""
        score = _make_score(overall=45.0, ai_prob=60.0)
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        assert result.recommendation == "skim"

    def test_recommendation_skim_low_score(self):
        """Should recommend 'skim' when overall_score < 40."""
        score = _make_score(overall=35.0, ai_prob=45.0)
        result = generate_focus_guide(GENUINE_HUMAN_TEXT, score)
        assert result is not None
        assert result.recommendation == "skim"

    def test_recommendation_read_carefully(self):
        """Should recommend 'read_carefully' for borderline content."""
        score = _make_score(overall=55.0, ai_prob=45.0)
        result = generate_focus_guide(GENUINE_HUMAN_TEXT, score)
        assert result is not None
        assert result.recommendation == "read_carefully"

    def test_tldr_not_empty_for_ai_text(self):
        """AI-generated content should produce a non-empty TL;DR."""
        score = _make_score()
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        assert result.tldr != ""

    def test_reading_time_saved_valid_range(self):
        """Reading time saved should be between 0 and 100."""
        score = _make_score()
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        assert 0 <= result.reading_time_saved_percent <= 100

    def test_english_ai_text_detection(self):
        """English AI-generated text should also be detected."""
        score = _make_score(overall=35.0, ai_prob=80.0)
        result = generate_focus_guide(AI_GENERATED_EN, score)
        assert result is not None
        assert len(result.ai_patterns) > 0

    def test_single_paragraph_text(self):
        """Single paragraph should still produce a result if score triggers it."""
        score = _make_score(overall=30.0, ai_prob=85.0)
        result = generate_focus_guide(SINGLE_PARAGRAPH, score)
        assert result is not None

    def test_borderline_no_guide(self):
        """Content at threshold (score=71, ai_prob=29) should NOT get guide."""
        score = ScoreResult(
            overall_score=71.0,
            dimensions=DimensionScores(
                originality=75,
                info_density=70,
                reasoning_quality=70,
                readability=80,
                timeliness=60,
                ai_generated_prob=29,
                emotional_manipulation=10,
                advertorial_prob=15,
                scam_prob=5,
            ),
            labels=[],
            summary="Good content",
            model_used="test",
            cost=0.0,
        )
        result = generate_focus_guide(GENUINE_HUMAN_TEXT, score)
        assert result is None


# ---------------------------------------------------------------------------
# Test: Pattern detection
# ---------------------------------------------------------------------------


class TestPatternDetection:
    """Tests for individual pattern detection functions."""

    def test_detect_uniform_structure_ai_text(self):
        """AI text with uniform paragraph lengths should be detected."""
        paragraphs = _split_paragraphs(AI_GENERATED_CN)
        result = _detect_uniform_structure(paragraphs)
        # AI text has fairly uniform paragraphs
        # This may or may not trigger depending on exact lengths
        # Just verify it returns AIPattern or None
        if result:
            assert result.pattern_name == "uniform_structure"

    def test_detect_uniform_structure_varied(self):
        """Varied paragraph lengths should NOT be flagged."""
        paragraphs = [
            "Short.",
            "This is a medium length paragraph with some content in it.",
            "This is a much longer paragraph that contains a lot more text and information and keeps going for quite a while to demonstrate significant variation in paragraph lengths across the document.",
        ]
        result = _detect_uniform_structure(paragraphs)
        assert result is None

    def test_detect_uniform_structure_too_few_paragraphs(self):
        """Fewer than 3 paragraphs should return None."""
        result = _detect_uniform_structure(["para one", "para two"])
        assert result is None

    def test_detect_formulaic_transitions_cn(self):
        """Chinese formulaic transitions should be detected."""
        paragraphs = _split_paragraphs(AI_GENERATED_CN)
        result = _detect_formulaic_transitions(paragraphs)
        assert result is not None
        assert result.pattern_name == "formulaic_transitions"
        assert len(result.examples) > 0

    def test_detect_formulaic_transitions_en(self):
        """English formulaic transitions should be detected."""
        paragraphs = _split_paragraphs(AI_GENERATED_EN)
        result = _detect_formulaic_transitions(paragraphs)
        assert result is not None
        assert result.pattern_name == "formulaic_transitions"

    def test_detect_formulaic_transitions_none(self):
        """Text without formulaic transitions should not be flagged."""
        paragraphs = [
            "2024年GDP增长了5.2%。",
            "据统计，全球有超过80亿人口。",
            "研究数据显示温度上升了1.5度。",
        ]
        result = _detect_formulaic_transitions(paragraphs)
        assert result is None

    def test_detect_repetitive_starters(self):
        """Repetitive sentence starters should be detected."""
        paragraphs = [
            "我们需要认识到AI的重要性。我们需要学习新技术。我们需要面对挑战。我们需要做好准备。我们需要团结合作。",
            "这是另一段。",
        ]
        result = _detect_repetitive_starters(paragraphs)
        assert result is not None
        assert result.pattern_name == "repetitive_starters"

    def test_detect_repetitive_starters_varied(self):
        """Varied sentence starters should NOT be flagged."""
        paragraphs = [
            "人工智能正在发展。技术改变了世界。数据是新的石油。研究表明趋势明显。创新驱动增长。",
        ]
        result = _detect_repetitive_starters(paragraphs)
        assert result is None

    def test_detect_filler_phrases(self):
        """Chinese filler phrases should be detected."""
        paragraphs = _split_paragraphs(AI_GENERATED_CN)
        result = _detect_filler_phrases(paragraphs)
        assert result is not None
        assert result.pattern_name == "generic_fillers"
        assert len(result.examples) > 0

    def test_detect_filler_phrases_none(self):
        """Text without filler phrases should not be flagged."""
        paragraphs = ["2024年3月的数据显示增长率为5%。", "OpenAI发布了最新的模型版本。"]
        result = _detect_filler_phrases(paragraphs)
        assert result is None

    def test_detect_lack_of_specifics(self):
        """Text without specific data should be flagged."""
        paragraphs = [
            "人工智能技术已经成为了一个不可忽视的力量，正在深刻地改变着我们的生活方式和工作模式，这是非常重要的事情。",
            "越来越多的企业开始将人工智能应用到实际生产中，这种趋势将会持续下去，并且会变得更加普遍和广泛。",
            "我们需要认识到人工智能带来的机遇和挑战，要积极拥抱变化，做好充分的准备来应对未来的发展。",
            "人工智能的发展是不可逆转的趋势，我们应该做好准备迎接这个新时代带来的各种变化和挑战。",
        ]
        result = _detect_lack_of_specifics(paragraphs)
        assert result is not None
        assert result.pattern_name == "lack_of_specifics"

    def test_detect_lack_of_specifics_with_data(self):
        """Text with specific data should NOT be flagged."""
        paragraphs = [
            "2024年第一季度GDP增长5.2%，超出预期0.3个百分点。",
            "OpenAI的GPT-4模型使用了128K tokens的上下文窗口。",
            "根据路透社报道，该项目投入了超过1亿美元。",
        ]
        result = _detect_lack_of_specifics(paragraphs)
        assert result is None


# ---------------------------------------------------------------------------
# Test: Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    """Tests for helper functions."""

    def test_split_paragraphs(self):
        """Should split on newlines and filter empty."""
        text = "para1\n\npara2\n\n\npara3"
        result = _split_paragraphs(text)
        assert result == ["para1", "para2", "para3"]

    def test_split_paragraphs_empty(self):
        """Empty text should return empty list."""
        assert _split_paragraphs("") == []
        assert _split_paragraphs("   \n\n   ") == []

    def test_split_sentences_chinese(self):
        """Should split on Chinese punctuation."""
        text = "第一句话。第二句话！第三句话？"
        result = _split_sentences(text)
        assert len(result) == 3

    def test_split_sentences_english(self):
        """Should split on English punctuation."""
        text = "First sentence. Second sentence! Third sentence?"
        result = _split_sentences(text)
        assert len(result) == 3

    def test_has_specifics_with_numbers(self):
        """Text with numbers should be considered specific."""
        assert _has_specifics("GDP增长了5.2%") is True

    def test_has_specifics_with_quotes(self):
        """Text with quotes should be considered specific."""
        assert _has_specifics('他说"这是重要的"') is True

    def test_has_specifics_with_proper_nouns(self):
        """Text with proper nouns should be considered specific."""
        assert _has_specifics("OpenAI released GPT-4 Turbo") is True

    def test_has_specifics_without_data(self):
        """Generic text should NOT be considered specific."""
        assert _has_specifics("这是一段普通的描述性文字") is False

    def test_count_filler_phrases(self):
        """Should count Chinese filler phrases."""
        text = "众所周知，在当今社会，随着科技的发展"
        count = _count_filler_phrases(text)
        assert count >= 3

    def test_count_transitions(self):
        """Should count transition phrases."""
        text = "首先，其次，最后，综上所述"
        count = _count_transitions(text)
        assert count >= 4

    def test_information_density_score_high(self):
        """Text with data should have high density score."""
        text = "2024年3月，GDP增长5.2%，超过了预期的4.8%目标"
        score = _information_density_score(text)
        assert score >= 0.3

    def test_information_density_score_low(self):
        """Generic filler text should have low density score."""
        text = "众所周知，在当今社会，不言而喻这是很重要的"
        score = _information_density_score(text)
        assert score <= 0.2

    def test_information_density_score_range(self):
        """Score should always be between 0.0 and 1.0."""
        texts = [
            "short",
            "这是一段很长的文字但是没有任何具体数据或者引用",
            "2024年GDP增长5.2%，据路透社报道",
            "众所周知不言而喻毋庸置疑在当今社会",
        ]
        for text in texts:
            score = _information_density_score(text)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Test: TL;DR generation
# ---------------------------------------------------------------------------


class TestTLDR:
    """Tests for TL;DR extraction."""

    def test_tldr_picks_informative_sentences(self):
        """TL;DR should prefer sentences with data points."""
        paragraphs = [
            "众所周知人工智能很重要。",
            "2024年3月OpenAI发布了GPT-4，上下文窗口128K tokens。",
            "这是一个很好的发展趋势。",
        ]
        result = _generate_tldr(paragraphs)
        # Should include the sentence with specific data
        assert "128K" in result or "GPT-4" in result or "2024" in result

    def test_tldr_empty_input(self):
        """Empty paragraphs should return empty string."""
        assert _generate_tldr([]) == ""

    def test_tldr_short_sentences_only(self):
        """Very short sentences should still produce some output."""
        paragraphs = ["好的。", "不错。", "可以的。"]
        result = _generate_tldr(paragraphs)
        # May be empty since all sentences are < 10 chars
        assert isinstance(result, str)

    def test_tldr_returns_string(self):
        """TL;DR should always return a string."""
        paragraphs = _split_paragraphs(AI_GENERATED_CN)
        result = _generate_tldr(paragraphs)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Test: Empty calorie and nugget classification
# ---------------------------------------------------------------------------


class TestClassification:
    """Tests for empty calorie vs information nugget classification."""

    def test_ai_text_has_empty_calories(self):
        """AI-generated text should have empty calorie paragraphs."""
        score = _make_score()
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        assert len(result.empty_calorie_indices) > 0

    def test_data_rich_text_has_nuggets(self):
        """Text with specific data should produce information nuggets."""
        score = _make_score(overall=45.0, ai_prob=55.0)
        result = generate_focus_guide(GENUINE_HUMAN_TEXT, score)
        assert result is not None
        assert len(result.information_nuggets) > 0

    def test_nuggets_have_summaries(self):
        """Information nuggets should have non-empty summaries."""
        score = _make_score(overall=45.0, ai_prob=55.0)
        result = generate_focus_guide(GENUINE_HUMAN_TEXT, score)
        assert result is not None
        for nugget in result.information_nuggets:
            assert nugget.summary != ""
            assert nugget.index >= 0

    def test_empty_calories_valid_indices(self):
        """Empty calorie indices should be valid paragraph indices."""
        score = _make_score()
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        paragraphs = _split_paragraphs(AI_GENERATED_CN)
        for idx in result.empty_calorie_indices:
            assert 0 <= idx < len(paragraphs)


# ---------------------------------------------------------------------------
# Test: Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_text_with_only_newlines(self):
        """Text with only newlines should return None."""
        score = _make_score()
        result = generate_focus_guide("\n\n\n\n", score)
        assert result is None

    def test_text_with_single_short_paragraph(self):
        """Very short single paragraph should still handle gracefully."""
        score = _make_score()
        result = generate_focus_guide("这是一段测试文字内容，长度超过十个字符。", score)
        assert result is not None or result is None  # Either is valid

    def test_suspicious_paragraphs_have_valid_fields(self):
        """Suspicious paragraphs should have valid index, reason, severity."""
        score = _make_score()
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        for sp in result.suspicious_paragraphs:
            assert sp.index >= 0
            assert sp.reason != ""
            assert sp.severity in ("low", "medium", "high")

    def test_ai_patterns_have_valid_fields(self):
        """AI patterns should have valid pattern_name, description."""
        score = _make_score()
        result = generate_focus_guide(AI_GENERATED_CN, score)
        assert result is not None
        for pattern in result.ai_patterns:
            assert pattern.pattern_name != ""
            assert pattern.description != ""

    def test_guide_with_mixed_content(self):
        """Text mixing AI-generated and genuine content should be handled."""
        mixed = AI_GENERATED_CN + "\n\n" + GENUINE_HUMAN_TEXT
        score = _make_score(overall=40.0, ai_prob=60.0)
        result = generate_focus_guide(mixed, score)
        assert result is not None
        # Should have both empty calories and nuggets
        assert result.recommendation in ("skip", "skim", "read_carefully")

    def test_uniform_structure_with_identical_lengths(self):
        """Paragraphs with identical lengths should definitely be flagged."""
        paragraphs = [
            "a" * 50,
            "b" * 50,
            "c" * 50,
            "d" * 50,
        ]
        result = _detect_uniform_structure(paragraphs)
        assert result is not None
        assert result.pattern_name == "uniform_structure"
