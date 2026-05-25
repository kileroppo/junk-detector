"""Tests for src/core/llm_judge.py error handling and edge cases."""

from __future__ import annotations

import json
import warnings
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.llm_judge import (
    _build_score_result,
    _default_score_result,
    _extract_json,
    _load_prompt_template,
    judge,
)
from src.models.score import ScoreResult, ScoringConfig


# --- _load_prompt_template tests ---


def test_load_prompt_template_deprecated():
    """_load_prompt_template emits DeprecationWarning and returns content."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = _load_prompt_template()
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "deprecated" in str(w[0].message).lower()
    assert isinstance(result, str)
    assert len(result) > 0


# --- _extract_json tests ---


def test_extract_json_from_code_fences():
    """Extract JSON from markdown code fences."""
    text = '```json\n{"key": "val", "num": 42}\n```'
    result = _extract_json(text)
    assert result == {"key": "val", "num": 42}


def test_extract_json_from_code_fences_no_lang():
    """Extract JSON from code fences without language specifier."""
    text = '```\n{"hello": "world"}\n```'
    result = _extract_json(text)
    assert result == {"hello": "world"}


def test_extract_json_plain_text():
    """Extract JSON embedded in plain text commentary."""
    text = 'here is the result: {"key": 1} that\'s it'
    result = _extract_json(text)
    assert result == {"key": 1}


def test_extract_json_full_text_fallback():
    """Parse valid JSON string directly as last resort."""
    text = '{"key": 1}'
    result = _extract_json(text)
    assert result == {"key": 1}


def test_extract_json_invalid_raises():
    """Raise JSONDecodeError when no valid JSON found."""
    with pytest.raises(json.JSONDecodeError):
        _extract_json("no json here at all")


# --- _build_score_result tests ---


def test_build_score_result():
    """Build ScoreResult from valid dimension dict."""
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
        "summary": "Good content",
        "confidence": 0.85,
        "labels": ["high_quality"],
    }
    result = _build_score_result(data, "test-model")
    assert isinstance(result, ScoreResult)
    assert result.model_used == "test-model"
    assert result.confidence == 0.85
    assert result.dimensions.originality == 75
    assert result.dimensions.scam_prob == 5
    assert result.summary == "Good content"
    assert result.labels == ["high_quality"]
    assert 0 <= result.overall_score <= 100


def test_build_score_result_defaults():
    """Build ScoreResult with missing optional fields uses defaults."""
    data = {
        "originality": 50,
        "info_density": 50,
        "reasoning_quality": 50,
        "readability": 50,
        "timeliness": 50,
        "ai_generated_prob": 50,
        "emotional_manipulation": 50,
        "advertorial_prob": 50,
        "scam_prob": 50,
    }
    result = _build_score_result(data, "model-x")
    assert result.summary == "评分完成"
    assert result.confidence == 0.8
    assert result.labels == []


# --- _default_score_result tests ---


def test_default_score_result():
    """Default result has confidence=0.1 and all dimensions=50."""
    result = _default_score_result("test-model")
    assert isinstance(result, ScoreResult)
    assert result.confidence == 0.1
    assert result.model_used == "test-model"
    assert result.overall_score == 50.0
    assert result.dimensions.originality == 50
    assert result.dimensions.info_density == 50
    assert result.dimensions.reasoning_quality == 50
    assert result.dimensions.readability == 50
    assert result.dimensions.timeliness == 50
    assert result.dimensions.ai_generated_prob == 50
    assert result.dimensions.emotional_manipulation == 50
    assert result.dimensions.advertorial_prob == 50
    assert result.dimensions.scam_prob == 50
    assert "解析失败" in result.labels


# --- judge() async tests ---


def _make_valid_response_json():
    """Return a valid JSON string for LLM scoring response."""
    return json.dumps({
        "originality": 75,
        "info_density": 60,
        "reasoning_quality": 70,
        "readability": 80,
        "timeliness": 50,
        "ai_generated_prob": 20,
        "emotional_manipulation": 10,
        "advertorial_prob": 15,
        "scam_prob": 5,
        "summary": "Good",
        "confidence": 0.85,
        "labels": [],
    })


def _make_mock_response(content: str, hidden_params=None):
    """Create a mock LLM response object."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_response._hidden_params = hidden_params
    return mock_response


@pytest.mark.asyncio
@patch("src.core.llm_judge.litellm.acompletion", new_callable=AsyncMock)
async def test_judge_empty_response_returns_default(mock_acompletion):
    """Empty LLM response triggers retries then returns default result."""
    mock_acompletion.return_value = _make_mock_response("", hidden_params=None)
    config = ScoringConfig(primary_model="test-model")
    result = await judge("some content", config)
    assert result.confidence == 0.1
    assert result.model_used == "test-model"
    # Should have attempted max_attempts=2 times
    assert mock_acompletion.call_count == 2


@pytest.mark.asyncio
@patch("src.core.llm_judge.litellm.acompletion", new_callable=AsyncMock)
async def test_judge_json_parse_failure_retries(mock_acompletion):
    """Garbled first response triggers retry; valid second response succeeds."""
    garbled_response = _make_mock_response("not valid json {{{", hidden_params=None)
    valid_response = _make_mock_response(_make_valid_response_json(), hidden_params=None)
    mock_acompletion.side_effect = [garbled_response, valid_response]

    config = ScoringConfig(primary_model="test-model")
    result = await judge("some content", config)
    assert result.confidence == 0.85
    assert result.dimensions.originality == 75
    assert mock_acompletion.call_count == 2


@pytest.mark.asyncio
@patch("src.core.llm_judge.litellm.acompletion", new_callable=AsyncMock)
async def test_judge_api_exception_breaks_loop(mock_acompletion):
    """Generic Exception breaks retry loop immediately, returns default."""
    mock_acompletion.side_effect = RuntimeError("Connection refused")
    config = ScoringConfig(primary_model="test-model")
    result = await judge("some content", config)
    assert result.confidence == 0.1
    assert result.model_used == "test-model"
    # Should only call once since generic Exception breaks the loop
    assert mock_acompletion.call_count == 1


@pytest.mark.asyncio
@patch("src.core.llm_judge.litellm.acompletion", new_callable=AsyncMock)
async def test_judge_cost_extraction(mock_acompletion):
    """Cost extracted from response._hidden_params."""
    mock_response = _make_mock_response(
        _make_valid_response_json(),
        hidden_params={"response_cost": 0.005},
    )
    mock_acompletion.return_value = mock_response
    config = ScoringConfig(primary_model="test-model")
    result = await judge("some content", config)
    assert result.cost == 0.005


@pytest.mark.asyncio
@patch("src.core.llm_judge.litellm.acompletion", new_callable=AsyncMock)
async def test_judge_no_hidden_params(mock_acompletion):
    """When _hidden_params is None, cost defaults to 0."""
    mock_response = _make_mock_response(
        _make_valid_response_json(),
        hidden_params=None,
    )
    mock_acompletion.return_value = mock_response
    config = ScoringConfig(primary_model="test-model")
    result = await judge("some content", config)
    assert result.cost == 0.0


@pytest.mark.asyncio
@patch("src.core.llm_judge.litellm.acompletion", new_callable=AsyncMock)
async def test_judge_hidden_params_empty_dict(mock_acompletion):
    """When _hidden_params is empty dict, cost defaults to 0."""
    mock_response = _make_mock_response(
        _make_valid_response_json(),
        hidden_params={},
    )
    mock_acompletion.return_value = mock_response
    config = ScoringConfig(primary_model="test-model")
    result = await judge("some content", config)
    assert result.cost == 0.0
