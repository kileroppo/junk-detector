"""Tests for rules-only mode: fast scoring without API key for obvious content."""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.core.fast_scorer import _rules_only_fast_result, score_fast
from src.core.rules import RuleResult
from src.models.score import FastScoreResult, ScoringConfig

runner = CliRunner()

# Obvious scam content with 5+ scam keywords
SCAM_CONTENT = "\u65e5\u5165\u8fc7\u4e07 \u8eba\u8d5a \u8d22\u5bcc\u81ea\u7531 \u9650\u65f6\u514d\u8d39 \u52a0\u5fae\u4fe1\u9886\u53d6"

# Clean/ambiguous content that needs LLM
CLEAN_CONTENT = "\u4eca\u5929\u5929\u6c14\u5f88\u597d\uff0c\u6211\u53bb\u516c\u56ed\u6563\u6b65\u4e86\u3002"


class TestRulesOnlyFastResult:
    """Test _rules_only_fast_result helper function."""

    def test_high_scam_returns_result(self):
        """High scam_prob with high confidence returns a FastScoreResult."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 95.0},
            confidence={"scam_prob": 0.95},
        )
        result = _rules_only_fast_result(rule_result, SCAM_CONTENT)

        assert result is not None
        assert isinstance(result, FastScoreResult)
        assert result.model_used == "rules_only"
        assert result.scam_prob == 95.0
        assert result.quick_verdict == 5.0  # 100 - 95
        assert result.originality == 50.0
        assert result.confidence == 0.95
        assert "\u89c4\u5219\u5f15\u64ce" in result.summary

    def test_high_emotional_returns_result(self):
        """High emotional_manipulation with high confidence returns result."""
        rule_result = RuleResult(
            matched_rules=["emotional_anxiety_and_punctuation"],
            dimension_overrides={"emotional_manipulation": 85.0},
            confidence={"emotional_manipulation": 0.9},
        )
        result = _rules_only_fast_result(rule_result, "test")

        assert result is not None
        assert result.emotional_manipulation == 85.0
        assert result.quick_verdict == 15.0  # 100 - 85
        assert result.model_used == "rules_only"

    def test_high_advertorial_returns_result(self):
        """High advertorial_prob with high confidence returns result."""
        rule_result = RuleResult(
            matched_rules=["advertorial_promo"],
            dimension_overrides={"advertorial_prob": 80.0},
            confidence={"advertorial_prob": 0.85},
        )
        result = _rules_only_fast_result(rule_result, "test")

        assert result is not None
        assert result.advertorial_prob == 80.0
        assert result.quick_verdict == 20.0  # 100 - 80
        assert result.model_used == "rules_only"

    def test_two_non_combo_rules_returns_result(self):
        """Two or more non-combo rules matched returns result."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords", "emotional_anxiety_phrases"],
            dimension_overrides={"scam_prob": 75.0, "emotional_manipulation": 70.0},
            confidence={"scam_prob": 0.8, "emotional_manipulation": 0.75},
        )
        result = _rules_only_fast_result(rule_result, "test")

        assert result is not None
        assert result.model_used == "rules_only"
        assert result.scam_prob == 75.0
        assert result.emotional_manipulation == 70.0

    def test_low_confidence_returns_none(self):
        """Low confidence rules do not trigger rules-only mode."""
        rule_result = RuleResult(
            matched_rules=["scam_keywords"],
            dimension_overrides={"scam_prob": 75.0},
            confidence={"scam_prob": 0.8},
        )
        # Only 1 non-combo rule, scam < 90, so shouldn't trigger
        result = _rules_only_fast_result(rule_result, "test")
        assert result is None

    def test_no_rules_returns_none(self):
        """No rules matched returns None."""
        rule_result = RuleResult()
        result = _rules_only_fast_result(rule_result, CLEAN_CONTENT)
        assert result is None

    def test_combo_only_rules_not_counted(self):
        """Only combo rules (without non-combo) do not trigger rules-only mode."""
        rule_result = RuleResult(
            matched_rules=["combo_engagement_bait"],
            dimension_overrides={"advertorial_prob": 20.0},
            confidence={"advertorial_prob": 0.1},
        )
        result = _rules_only_fast_result(rule_result, "test")
        assert result is None


class TestScoreFastRulesPreCheck:
    """Test that score_fast uses rules pre-check before LLM."""

    @pytest.mark.asyncio
    async def test_scam_content_returns_without_llm(self):
        """Obvious scam content returns rules-based result without calling LLM."""
        # No API key, no LLM mock needed - rules should handle it
        config = ScoringConfig(primary_model="deepseek/deepseek-chat")
        result = await score_fast(SCAM_CONTENT, config=config)

        assert isinstance(result, FastScoreResult)
        assert result.model_used == "rules_only"
        assert result.scam_prob >= 90.0
        assert result.quick_verdict <= 10.0
        assert result.confidence >= 0.9

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_clean_content_still_calls_llm(self, mock_acompletion):
        """Clean content that rules cannot handle still calls LLM."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "scam_prob": 5,
                "advertorial_prob": 10,
                "emotional_manipulation": 5,
                "originality": 70,
                "quick_verdict": 80,
                "summary": "Normal content",
            }
        )
        mock_response._hidden_params = {}
        mock_acompletion.return_value = mock_response

        config = ScoringConfig(primary_model="test-model")
        result = await score_fast(CLEAN_CONTENT, config=config)

        assert result.model_used == "test-model"
        mock_acompletion.assert_called_once()

    @pytest.mark.asyncio
    async def test_scam_content_no_api_key_succeeds(self):
        """Scam content works even without any API key environment variable."""
        # Ensure no API keys are set
        env_backup = {}
        for key in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            if key in os.environ:
                env_backup[key] = os.environ.pop(key)

        try:
            config = ScoringConfig(primary_model="deepseek/deepseek-chat")
            result = await score_fast(SCAM_CONTENT, config=config)

            assert result.model_used == "rules_only"
            assert result.scam_prob >= 90.0
        finally:
            # Restore env
            os.environ.update(env_backup)


class TestQuickCLIRulesOnly:
    """Test that the quick CLI command works without API key for scam content."""

    def test_quick_scam_without_api_key(self):
        """quick --text with scam content works without DEEPSEEK_API_KEY."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_CONTENT],
            env={"DEEPSEEK_API_KEY": ""},
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        # Auto rules-only engaged; content triggers 1 rule only,
        # so should_skip_llm returns False -> uncertain verdict (score 50)
        assert "\u26a0\ufe0f" in result.output

    def test_quick_scam_json_without_api_key(self):
        """quick --text --json with scam content returns rules_only model."""
        result = runner.invoke(
            app,
            ["quick", "--text", SCAM_CONTENT, "--json"],
            env={"DEEPSEEK_API_KEY": ""},
        )

        assert result.exit_code == 1, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        # With auto rules-only, should_skip_llm requires 3+ rules.
        # SCAM_CONTENT only triggers 1 rule so gets uncertain verdict (50).
        assert data["quick_verdict"] <= 50.0

    def test_quick_clean_content_fails_without_api_key(self):
        """quick --text with clean content fails gracefully without API key."""
        result = runner.invoke(
            app,
            ["quick", "--text", CLEAN_CONTENT],
            env={"DEEPSEEK_API_KEY": ""},
        )

        # Auto rules-only is engaged because no API key.
        # Clean content gets uncertain verdict (score 50 < 60) -> exit 1
        assert result.exit_code == 1


class TestScoreFastFlagRulesOnly:
    """Test --fast flag on score command also works without API key."""

    def test_score_fast_scam_without_api_key(self):
        """score --fast --text with scam content works without DEEPSEEK_API_KEY."""
        result = runner.invoke(
            app,
            ["score", "--fast", "--text", SCAM_CONTENT],
            env={"DEEPSEEK_API_KEY": ""},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        assert "\U0001f6a8" in result.output or "\u26a0\ufe0f" in result.output

    def test_score_fast_scam_json_without_api_key(self):
        """score --fast --text --json with scam content returns rules_only."""
        result = runner.invoke(
            app,
            ["score", "--fast", "--text", SCAM_CONTENT, "--json"],
            env={"DEEPSEEK_API_KEY": ""},
        )

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["model_used"] == "rules_only"
        assert data["scam_prob"] >= 90.0
