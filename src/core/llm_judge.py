"""LLM Judge module — calls LLM to score content quality."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

import litellm

from src.models.score import DimensionScores, ScoreResult, ScoringConfig

logger = logging.getLogger(__name__)

# Resolve prompt template path relative to project root
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "score_content.txt"


def _load_prompt_template() -> str:
    """Load the scoring prompt template from disk."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response text.

    Handles cases where the model wraps JSON in markdown code fences
    or adds extra commentary.
    """
    # Try to find JSON within code fences first
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()

    # Try to find a JSON object directly
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    # Last resort: try parsing the whole text
    return json.loads(text)


def _build_score_result(data: dict, model: str) -> ScoreResult:
    """Convert parsed JSON dict into a ScoreResult, computing overall_score."""
    dimensions = DimensionScores(
        originality=data["originality"],
        info_density=data["info_density"],
        reasoning_quality=data["reasoning_quality"],
        readability=data["readability"],
        timeliness=data["timeliness"],
        ai_generated_prob=data["ai_generated_prob"],
        emotional_manipulation=data["emotional_manipulation"],
        advertorial_prob=data["advertorial_prob"],
        scam_prob=data["scam_prob"],
    )

    # Compute overall score using default weights
    config = ScoringConfig()
    weighted_sum = 0.0
    total_weight = 0.0
    for dim, weight in config.weights.items():
        score = getattr(dimensions, dim)
        if weight > 0:
            weighted_sum += score * weight
            total_weight += weight * 100
        else:
            # Negative dimensions: higher score → lower overall
            weighted_sum += (100 - score) * abs(weight)
            total_weight += abs(weight) * 100

    overall = (weighted_sum / total_weight) * 100 if total_weight > 0 else 50.0
    overall = max(0.0, min(100.0, overall))

    return ScoreResult(
        overall_score=round(overall, 1),
        dimensions=dimensions,
        labels=data.get("labels", []),
        summary=data.get("summary", "评分完成"),
        confidence=float(data.get("confidence", 0.8)),
        model_used=model,
        scored_at=datetime.now(),
    )


def _default_score_result(model: str) -> ScoreResult:
    """Return a low-confidence default when parsing completely fails."""
    dimensions = DimensionScores(
        originality=50,
        info_density=50,
        reasoning_quality=50,
        readability=50,
        timeliness=50,
        ai_generated_prob=50,
        emotional_manipulation=50,
        advertorial_prob=50,
        scam_prob=50,
    )
    return ScoreResult(
        overall_score=50.0,
        dimensions=dimensions,
        labels=["解析失败"],
        summary="LLM响应解析失败，返回默认评分",
        confidence=0.1,
        model_used=model,
        scored_at=datetime.now(),
    )


async def judge(content: str, config: ScoringConfig) -> ScoreResult:
    """Score content using an LLM judge.

    Args:
        content: The text content to evaluate.
        config: Scoring configuration (contains model name, etc.).

    Returns:
        ScoreResult with dimension scores, labels, and summary.
    """
    model = config.primary_model
    template = _load_prompt_template()
    prompt = template.replace("{content}", content)

    messages = [{"role": "user", "content": prompt}]

    max_attempts = 2
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
            )

            raw_text = response.choices[0].message.content
            if not raw_text:
                raise ValueError("Empty response from LLM")

            data = _extract_json(raw_text)
            result = _build_score_result(data, model)

            # Attach cost if available
            hidden = getattr(response, "_hidden_params", None)
            if hidden and isinstance(hidden, dict):
                cost = hidden.get("response_cost", 0.0)
                if cost:
                    result.cost = cost

            return result

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            last_error = e
            logger.warning(
                "Attempt %d/%d: Failed to parse LLM response: %s",
                attempt + 1,
                max_attempts,
                e,
            )
            continue

        except Exception as e:
            last_error = e
            logger.error("LLM API call failed: %s", e)
            break

    # All attempts failed — return low-confidence default
    logger.error(
        "All attempts to score content failed. Last error: %s", last_error
    )
    return _default_score_result(model)
