"""Tests for Intelligence Layer (FEAT-003).

Tests for:
- Rhythm fingerprint analysis (uniform vs diverse text)
- Adaptive feedback weights
- Source warning badge (mocked)
- Rule explanation in result template
- Focus guide rhythm integration
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Rhythm Fingerprint Tests
# ---------------------------------------------------------------------------


class TestRhythmFingerprint:
    """Tests for src/core/rhythm_fingerprint.py."""

    def test_rhythm_uniform_text(self):
        """Highly uniform text (same length paragraphs) should have high rhythm_uniformity."""
        from src.core.rhythm_fingerprint import analyze_rhythm

        # Create text with very uniform paragraph lengths
        paragraph = "这是一段测试文字用来检测写作节奏的均匀程度。这段话长度经过控制。"
        uniform_text = "\n".join([paragraph] * 6)

        result = analyze_rhythm(uniform_text)

        assert result.rhythm_uniformity > 70
        assert result.paragraph_count == 6

    def test_rhythm_diverse_text(self):
        """Diverse human-like text should have low rhythm_uniformity."""
        from src.core.rhythm_fingerprint import analyze_rhythm

        # Create text with very different paragraph lengths
        diverse_text = (
            "短句。\n"
            "这是一段中等长度的文字，包含了一些信息和描述，试图模拟正常的写作风格。\n"
            "而这一段则是一个非常非常长的段落，里面包含了大量的信息、描述、分析和各种各样的内容，"
            "目的是为了创造出一种人类写作中常见的段落长度差异，因为人类写作时往往不会刻意控制每个段落的长度，"
            "而是根据内容需要自然地展开，有时候一个段落可能只有几个字，有时候则可能洋洋洒洒写上几百字。\n"
            "OK。\n"
            "最后一段中等偏短的收尾总结。"
        )

        result = analyze_rhythm(diverse_text)

        assert result.rhythm_uniformity < 40
        assert result.paragraph_count == 5

    def test_rhythm_short_text(self):
        """Very short text returns reasonable defaults."""
        from src.core.rhythm_fingerprint import analyze_rhythm

        result = analyze_rhythm("短")

        assert result.rhythm_uniformity == 50.0
        assert result.sentence_diversity == 50.0
        assert result.topic_drift == 50.0
        assert result.paragraph_count == 1

    def test_rhythm_empty_text(self):
        """Empty text returns neutral defaults."""
        from src.core.rhythm_fingerprint import analyze_rhythm

        result = analyze_rhythm("")

        assert result.rhythm_uniformity == 50.0
        assert result.paragraph_count == 0

    def test_sentence_diversity_uniform(self):
        """Text with uniform sentence lengths should have low diversity."""
        from src.core.rhythm_fingerprint import analyze_rhythm

        # All sentences roughly the same length
        sentences = "这是一个句子。那是一个句子。她是一个人物。他是一个学生。我是一个工人。你是一个教师。"
        text = sentences + "\n" + sentences + "\n" + sentences

        result = analyze_rhythm(text)
        # Low diversity expected for uniform sentences
        assert result.sentence_diversity < 60

    def test_sentence_diversity_varied(self):
        """Text with varied sentence lengths should have high diversity."""
        from src.core.rhythm_fingerprint import analyze_rhythm

        text = (
            "短。这是一个比较长的句子包含了更多的内容和信息。好。\n"
            "这段话里有很多不同长度的句子，有的特别长有的特别短，模拟了人类自然写作的风格特征和习惯。嗯。对。\n"
            "第三段也是如此。这里面的句子长短不一，完全随机地分布着各种长度的表达。是的！"
        )

        result = analyze_rhythm(text)
        assert result.sentence_diversity > 40


# ---------------------------------------------------------------------------
# Adaptive Weights Tests
# ---------------------------------------------------------------------------


class TestAdaptiveWeights:
    """Tests for src/core/adaptive_weights.py."""

    def test_save_and_get_weight_adjustment(self, tmp_db_path):
        """Save a weight adjustment and verify it's retrieved correctly."""
        from src.core.adaptive_weights import (
            get_adjusted_weights,
            save_weight_adjustment,
        )

        base_weights = {"scam_prob": -1.2, "originality": 1.0}

        # Save an adjustment
        save_weight_adjustment(
            user_id="test_user",
            dimension="scam_prob",
            adjustment=-0.05,
            db_path=tmp_db_path,
        )

        result = get_adjusted_weights(
            user_id="test_user",
            base_weights=base_weights,
            db_path=tmp_db_path,
        )

        assert result["scam_prob"] == pytest.approx(-1.25, abs=0.001)
        assert result["originality"] == 1.0  # unchanged

    def test_adaptive_weights_feedback_wrong(self, tmp_db_path):
        """When user marks a high score as 'wrong', weight adjustments are stored."""
        from src.core.adaptive_weights import (
            compute_feedback_adjustments,
            get_adjusted_weights,
            save_weight_adjustment,
        )

        # Simulate: score was 75 (high), user says it's wrong (should be junk)
        dimensions = {
            "originality": 70,
            "info_density": 65,
            "reasoning_quality": 70,
            "readability": 80,
            "timeliness": 50,
            "ai_generated_prob": 20,  # low = didn't catch it
            "emotional_manipulation": 15,
            "advertorial_prob": 10,
            "scam_prob": 5,
        }

        adjustments = compute_feedback_adjustments("wrong", 75.0, dimensions)

        # Should have adjustments for negative dimensions that were low
        assert "ai_generated_prob" in adjustments
        assert adjustments["ai_generated_prob"] == -0.05

        # Save adjustments and verify
        for dim, adj in adjustments.items():
            save_weight_adjustment("user1", dim, adj, db_path=tmp_db_path)

        result = get_adjusted_weights("user1", db_path=tmp_db_path)
        # ai_generated_prob base is -0.8, adjusted by -0.05 = -0.85
        assert result["ai_generated_prob"] == pytest.approx(-0.85, abs=0.001)

    def test_get_adjusted_weights_no_adjustments(self, tmp_db_path):
        """Without any stored adjustments, returns base weights unchanged."""
        from src.core.adaptive_weights import get_adjusted_weights

        base = {"originality": 1.0, "scam_prob": -1.2}
        result = get_adjusted_weights("nobody", base_weights=base, db_path=tmp_db_path)

        assert result == base

    def test_feedback_correct_no_adjustments(self):
        """Correct verdict should produce no adjustments."""
        from src.core.adaptive_weights import compute_feedback_adjustments

        adjustments = compute_feedback_adjustments("correct", 50.0, {"originality": 50})
        assert adjustments == {}

    def test_cumulative_adjustments(self, tmp_db_path):
        """Multiple adjustments for same dimension should accumulate."""
        from src.core.adaptive_weights import (
            get_adjusted_weights,
            save_weight_adjustment,
        )

        save_weight_adjustment("user2", "scam_prob", -0.05, db_path=tmp_db_path)
        save_weight_adjustment("user2", "scam_prob", -0.05, db_path=tmp_db_path)
        save_weight_adjustment("user2", "scam_prob", -0.05, db_path=tmp_db_path)

        result = get_adjusted_weights(
            "user2",
            base_weights={"scam_prob": -1.2},
            db_path=tmp_db_path,
        )
        # -1.2 + (-0.15) = -1.35
        assert result["scam_prob"] == pytest.approx(-1.35, abs=0.001)


# ---------------------------------------------------------------------------
# Source Warning Badge Tests
# ---------------------------------------------------------------------------


class TestSourceWarningBadge:
    """Tests for source warning badge in router."""

    def test_source_warning_blacklisted(self, monkeypatch, set_api_key):
        """When domain is blacklisted, result includes warning."""
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from src.api.app import app

        # Mock is_blacklisted to return True
        monkeypatch.setattr(
            "src.core.source_reputation.is_blacklisted",
            lambda domain, config_path=None: True,
        )

        from src.models.score import Content, DimensionScores, InputType, ScoreResult

        mock_content = Content(
            input_type=InputType.URL,
            text="test content for blacklisted domain",
            source_url="https://scam-site.com/article",
            title="Test",
            content_hash="abc123",
        )

        mock_result = ScoreResult(
            overall_score=45.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=40,
                reasoning_quality=50,
                readability=60,
                timeliness=50,
                ai_generated_prob=30,
                emotional_manipulation=20,
                advertorial_prob=10,
                scam_prob=60,
            ),
            labels=["疑似骗局"],
            summary="Test summary",
            rule_hits=["scam_keywords"],
            dimension_sources={"scam_prob": "rule"},
        )

        with patch("src.extractors.web.extract_from_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = mock_content
            with patch("src.core.scorer.score", new_callable=AsyncMock) as mock_score:
                mock_score.return_value = mock_result
                with patch("src.storage.db.save"):
                    with TestClient(app) as client:
                        response = client.post(
                            "/score-submit",
                            data={"input_type": "url", "url": "https://scam-site.com/article"},
                        )

        assert response.status_code == 200
        assert "来源已列入黑名单" in response.text

    def test_source_warning_not_present_for_clean_domain(self, monkeypatch, set_api_key):
        """When domain is not blacklisted, no warning shown."""
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from src.api.app import app

        monkeypatch.setattr(
            "src.core.source_reputation.is_blacklisted",
            lambda domain, config_path=None: False,
        )
        monkeypatch.setattr(
            "src.core.source_reputation.check_auto_blacklist",
            lambda domain, db_path="junk_detector.db", config_path=None: False,
        )

        from src.models.score import Content, DimensionScores, InputType, ScoreResult

        mock_content = Content(
            input_type=InputType.URL,
            text="good content from trusted domain",
            source_url="https://trusted-site.com/article",
            title="Good Article",
            content_hash="def456",
        )

        mock_result = ScoreResult(
            overall_score=80.0,
            dimensions=DimensionScores(
                originality=85,
                info_density=75,
                reasoning_quality=80,
                readability=90,
                timeliness=70,
                ai_generated_prob=10,
                emotional_manipulation=5,
                advertorial_prob=5,
                scam_prob=2,
            ),
            labels=["高质量原创"],
            summary="Great article",
            rule_hits=[],
            dimension_sources={},
        )

        with patch("src.extractors.web.extract_from_url", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = mock_content
            with patch("src.core.scorer.score", new_callable=AsyncMock) as mock_score:
                mock_score.return_value = mock_result
                with patch("src.storage.db.save"):
                    with TestClient(app) as client:
                        response = client.post(
                            "/score-submit",
                            data={"input_type": "url", "url": "https://trusted-site.com/article"},
                        )

        assert response.status_code == 200
        assert "来源已列入黑名单" not in response.text
        assert "该来源历史评分较低" not in response.text


# ---------------------------------------------------------------------------
# Rule Explanation Tests
# ---------------------------------------------------------------------------


class TestRuleExplanation:
    """Tests for 'Why This Score' rule explanation in result template."""

    def test_rule_explanation_in_result(self, monkeypatch, set_api_key):
        """Score result with rule_hits shows them in the template."""
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from src.api.app import app
        from src.models.score import Content, DimensionScores, InputType, ScoreResult

        mock_content = Content(
            input_type=InputType.TEXT,
            text="日入过万！限时免费！零成本稳赚不赔！",
            title="Scam Test",
            content_hash="rule_test_hash",
        )

        mock_result = ScoreResult(
            overall_score=15.0,
            dimensions=DimensionScores(
                originality=20,
                info_density=10,
                reasoning_quality=15,
                readability=50,
                timeliness=30,
                ai_generated_prob=40,
                emotional_manipulation=70,
                advertorial_prob=60,
                scam_prob=90,
            ),
            labels=["疑似骗局", "情绪操纵"],
            summary="Likely scam content",
            rule_hits=["scam_keywords", "emotional_manipulation_high"],
            dimension_sources={"scam_prob": "rule", "emotional_manipulation": "rule", "originality": "llm"},
        )

        with patch("src.extractors.text.extract_from_text") as mock_extract:
            mock_extract.return_value = mock_content
            with patch("src.core.scorer.score", new_callable=AsyncMock) as mock_score:
                mock_score.return_value = mock_result
                with patch("src.storage.db.save"):
                    with TestClient(app) as client:
                        response = client.post(
                            "/score-submit",
                            data={"input_type": "text", "text": "日入过万！限时免费！"},
                        )

        assert response.status_code == 200
        # Check that the "Why This Score" section is present
        assert "为什么是这个分数" in response.text
        # Check that rule hits are shown
        assert "scam_keywords" in response.text
        assert "emotional_manipulation_high" in response.text
        # Check dimension sources
        assert "rule" in response.text


# ---------------------------------------------------------------------------
# Focus Guide Rhythm Integration Tests
# ---------------------------------------------------------------------------


class TestFocusGuideRhythm:
    """Tests for rhythm fingerprint integration in focus guide."""

    def test_focus_guide_rhythm_integration(self):
        """Focus guide includes rhythm fingerprint for analyzed text."""
        from src.core.focus_guide import generate_focus_guide
        from src.models.score import DimensionScores, ScoreResult

        # Create uniform text that triggers focus guide
        paragraph = "这是一段测试文字用来检测AI生成的内容质量问题。这段话长度经过精心控制以保持一致。"
        uniform_text = "\n".join([paragraph] * 8)

        result = ScoreResult(
            overall_score=35.0,
            dimensions=DimensionScores(
                originality=30,
                info_density=25,
                reasoning_quality=30,
                readability=50,
                timeliness=40,
                ai_generated_prob=75,
                emotional_manipulation=20,
                advertorial_prob=15,
                scam_prob=5,
            ),
            labels=["可能AI生成"],
            summary="AI-generated content detected",
        )

        guide = generate_focus_guide(uniform_text, result)

        assert guide is not None
        assert guide.rhythm_fingerprint is not None
        assert guide.rhythm_fingerprint.rhythm_uniformity > 65
        assert guide.rhythm_fingerprint.paragraph_count == 8

    def test_focus_guide_no_rhythm_for_good_content(self):
        """Focus guide returns None for high-quality content."""
        from src.core.focus_guide import generate_focus_guide
        from src.models.score import DimensionScores, ScoreResult

        result = ScoreResult(
            overall_score=85.0,
            dimensions=DimensionScores(
                originality=90,
                info_density=80,
                reasoning_quality=85,
                readability=90,
                timeliness=70,
                ai_generated_prob=10,
                emotional_manipulation=5,
                advertorial_prob=5,
                scam_prob=2,
            ),
            labels=["高质量原创"],
            summary="High quality content",
        )

        guide = generate_focus_guide("Some text content here.", result)

        # Should return None for high-quality content
        assert guide is None
