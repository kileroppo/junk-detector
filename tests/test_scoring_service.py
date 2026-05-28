"""Tests for src.core.scoring_service module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scoring_service import ScoringReport, score_with_full_report
from src.models.score import DimensionScores, ScoreResult, ScoringConfig


def _make_score_result(overall_score: float = 65.0, ai_generated_prob: float = 40.0) -> ScoreResult:
    """Helper to create a ScoreResult for testing."""
    return ScoreResult(
        overall_score=overall_score,
        dimensions=DimensionScores(
            originality=70,
            info_density=60,
            reasoning_quality=65,
            readability=75,
            timeliness=50,
            ai_generated_prob=ai_generated_prob,
            emotional_manipulation=10,
            advertorial_prob=15,
            scam_prob=5,
        ),
        labels=["test-label"],
        summary="Test summary",
        confidence=0.9,
        model_used="test-model",
        cost=0.001,
        scored_at=datetime(2025, 1, 15, 12, 0, 0),
        rule_hits=["rule_a", "rule_b"],
        dimension_sources={"originality": "llm", "scam_prob": "rule"},
    )


class TestScoringReport:
    """Tests for ScoringReport model."""

    def test_scoring_report_fields(self):
        """ScoringReport has all expected fields."""
        result = _make_score_result()
        report = ScoringReport(
            result=result,
            rule_score=55.0,
            llm_score=65.0,
            divergence_warning=False,
            focus_guide=None,
            source_warning=None,
            rule_hits=["rule_a"],
            dimension_sources={"originality": "llm"},
            rules_fired=True,
            score_divergence=10.0,
        )
        assert report.rule_score == 55.0
        assert report.llm_score == 65.0
        assert report.divergence_warning is False
        assert report.rules_fired is True
        assert report.score_divergence == 10.0

    def test_scoring_report_optional_fields_default(self):
        """Optional fields default to None/empty."""
        result = _make_score_result()
        report = ScoringReport(
            result=result,
            rule_score=50.0,
            llm_score=60.0,
            divergence_warning=False,
        )
        assert report.focus_guide is None
        assert report.source_warning is None
        assert report.rule_hits == []
        assert report.dimension_sources == {}
        assert report.rules_fired is False
        assert report.score_divergence == 0.0


class TestScoreWithFullReport:
    """Tests for score_with_full_report function."""

    @pytest.mark.asyncio
    async def test_basic_report_assembly(self):
        """score_with_full_report returns ScoringReport with all fields."""
        mock_result = _make_score_result(overall_score=75.0, ai_generated_prob=10.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=70.0),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("test content")

            assert isinstance(report, ScoringReport)
            assert report.result == mock_result
            assert report.llm_score == 75.0
            assert report.rule_score == 70.0
            assert report.rule_hits == ["rule_a", "rule_b"]
            assert report.dimension_sources == {"originality": "llm", "scam_prob": "rule"}

    @pytest.mark.asyncio
    async def test_focus_guide_generated_when_score_low(self):
        """Focus guide is generated when overall_score < 70."""
        mock_result = _make_score_result(overall_score=55.0, ai_generated_prob=10.0)
        mock_guide = MagicMock()
        mock_guide.model_dump.return_value = {"suggestions": ["improve structure"]}

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=50.0),
            patch("src.core.focus_guide.generate_focus_guide", return_value=mock_guide) as mock_fg,
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("low quality content")

            assert report.focus_guide == {"suggestions": ["improve structure"]}
            mock_fg.assert_called_once()

    @pytest.mark.asyncio
    async def test_focus_guide_generated_when_ai_prob_high(self):
        """Focus guide is generated when ai_generated_prob > 30."""
        mock_result = _make_score_result(overall_score=80.0, ai_generated_prob=50.0)
        mock_guide = MagicMock()
        mock_guide.model_dump.return_value = {"ai_patterns": ["formulaic"]}

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=75.0),
            patch("src.core.focus_guide.generate_focus_guide", return_value=mock_guide),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("ai-like content")

            assert report.focus_guide == {"ai_patterns": ["formulaic"]}

    @pytest.mark.asyncio
    async def test_focus_guide_not_generated_when_good(self):
        """Focus guide is None when score >= 70 and ai_prob <= 30."""
        mock_result = _make_score_result(overall_score=85.0, ai_generated_prob=10.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=80.0),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("high quality content")

            assert report.focus_guide is None

    @pytest.mark.asyncio
    async def test_source_warning_blacklisted(self):
        """Source warning generated for blacklisted domain."""
        mock_result = _make_score_result(overall_score=85.0, ai_generated_prob=10.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=80.0),
            patch("src.core.source_reputation.is_blacklisted", return_value=True),
            patch("src.core.source_reputation.check_auto_blacklist", return_value=False),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report(
                "content", source_url="https://spam-site.com/article"
            )

            assert report.source_warning is not None
            assert report.source_warning["level"] == "blacklisted"

    @pytest.mark.asyncio
    async def test_source_warning_low_reputation(self):
        """Source warning generated for low reputation domain."""
        mock_result = _make_score_result(overall_score=85.0, ai_generated_prob=10.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=80.0),
            patch("src.core.source_reputation.is_blacklisted", return_value=False),
            patch("src.core.source_reputation.check_auto_blacklist", return_value=True),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report(
                "content", source_url="https://www.low-rep.com/post"
            )

            assert report.source_warning is not None
            assert report.source_warning["level"] == "low_reputation"

    @pytest.mark.asyncio
    async def test_divergence_warning_when_large(self):
        """Divergence warning set when rule_score and llm_score differ > 20 and rules fired."""
        mock_result = _make_score_result(overall_score=80.0, ai_generated_prob=5.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=50.0),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={"scam_prob": 80.0},
                matched_rules=["scam_keywords"],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("suspicious content")

            assert report.divergence_warning is True
            assert report.rules_fired is True
            assert report.score_divergence == 30.0

    @pytest.mark.asyncio
    async def test_no_divergence_warning_when_no_rules_fired(self):
        """No divergence warning when rules did not fire even if scores differ."""
        mock_result = _make_score_result(overall_score=80.0, ai_generated_prob=5.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=50.0),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("content")

            assert report.divergence_warning is False
            assert report.rules_fired is False

    @pytest.mark.asyncio
    async def test_no_source_warning_without_url(self):
        """No source warning when source_url is None."""
        mock_result = _make_score_result(overall_score=85.0, ai_generated_prob=10.0)

        with (
            patch("src.core.scorer.score", new_callable=AsyncMock, return_value=mock_result),
            patch("src.core.rules.apply_rules") as mock_rules,
            patch("src.core.config.load_config") as mock_config,
            patch("src.core.scorer._calculate_overall", return_value=80.0),
        ):
            mock_rules.return_value = MagicMock(
                dimension_overrides={},
                matched_rules=[],
            )
            mock_config.return_value = ScoringConfig()

            report = await score_with_full_report("content", source_url=None)

            assert report.source_warning is None
