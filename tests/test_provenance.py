"""Tests for scoring provenance fields."""

from src.models.score import DimensionScores, ScoreResult


class TestScoringProvenance:
    """Tests that ScoreResult includes provenance metadata fields."""

    def test_score_result_has_scored_by_field(self):
        """ScoreResult model should have scored_by field with default 'rules'."""
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=50,
                emotional_manipulation=50,
                advertorial_prob=50,
                scam_prob=50,
            ),
            labels=[],
            summary="test",
        )
        assert hasattr(result, "scored_by")
        assert result.scored_by == "rules"

    def test_score_result_has_duration_ms_field(self):
        """ScoreResult model should have duration_ms field with default 0."""
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=50,
                emotional_manipulation=50,
                advertorial_prob=50,
                scam_prob=50,
            ),
            labels=[],
            summary="test",
        )
        assert hasattr(result, "duration_ms")
        assert result.duration_ms == 0

    def test_score_result_has_cost_usd_field(self):
        """ScoreResult model should have cost_usd field with default 0.0."""
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=50,
                emotional_manipulation=50,
                advertorial_prob=50,
                scam_prob=50,
            ),
            labels=[],
            summary="test",
        )
        assert hasattr(result, "cost_usd")
        assert result.cost_usd == 0.0

    def test_score_result_scored_by_can_be_set(self):
        """ScoreResult scored_by field should accept a model name."""
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=50,
                emotional_manipulation=50,
                advertorial_prob=50,
                scam_prob=50,
            ),
            labels=[],
            summary="test",
            scored_by="deepseek/deepseek-chat",
            duration_ms=150,
            cost_usd=0.001,
        )
        assert result.scored_by == "deepseek/deepseek-chat"
        assert result.duration_ms == 150
        assert result.cost_usd == 0.001

    def test_score_result_serialization_includes_provenance(self):
        """ScoreResult.model_dump() should include provenance fields."""
        result = ScoreResult(
            overall_score=50.0,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=50,
                emotional_manipulation=50,
                advertorial_prob=50,
                scam_prob=50,
            ),
            labels=[],
            summary="test",
            scored_by="gpt-4",
            duration_ms=200,
        )
        data = result.model_dump()
        assert "scored_by" in data
        assert "duration_ms" in data
        assert "cost_usd" in data
        assert data["scored_by"] == "gpt-4"
        assert data["duration_ms"] == 200
