"""LLM Judge module — calls LLM to score content quality."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime

import httpx
import litellm

from src.core.prompt_loader import get_prompt_template, get_system_prompt
from src.models.score import DimensionScores, ScoreResult, ScoringConfig

logger = logging.getLogger(__name__)


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

    def _clamp_score(val, name: str) -> int:
        val = int(val)
        if val < 0 or val > 100:
            logger.warning("Dimension %s out of range: %d, clamping to [0, 100]", name, val)
            return max(0, min(100, val))
        return val

    dimensions = DimensionScores(
        originality=_clamp_score(data["originality"], "originality"),
        info_density=_clamp_score(data["info_density"], "info_density"),
        reasoning_quality=_clamp_score(data["reasoning_quality"], "reasoning_quality"),
        readability=_clamp_score(data["readability"], "readability"),
        timeliness=_clamp_score(data["timeliness"], "timeliness"),
        ai_generated_prob=_clamp_score(data["ai_generated_prob"], "ai_generated_prob"),
        emotional_manipulation=_clamp_score(data["emotional_manipulation"], "emotional_manipulation"),
        advertorial_prob=_clamp_score(data["advertorial_prob"], "advertorial_prob"),
        scam_prob=_clamp_score(data["scam_prob"], "scam_prob"),
    )

    # Clamp confidence to [0, 1]
    confidence = float(data.get("confidence", 0.8))
    if confidence < 0 or confidence > 1:
        logger.warning("Confidence out of range: %.2f, clamping to [0, 1]", confidence)
        confidence = max(0.0, min(1.0, confidence))

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
        confidence=confidence,
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


async def judge(content: str, config: ScoringConfig, language: str = "zh") -> ScoreResult:
    """Score content using an LLM judge.

    Args:
        content: The text content to evaluate.
        config: Scoring configuration (contains model name, etc.).
        language: Language code for prompt template ("zh" or "en"). Defaults to "zh".

    Returns:
        ScoreResult with dimension scores, labels, and summary.
    """
    model = config.primary_model
    system_prompt = get_system_prompt(language)
    user_content = f"<content_to_evaluate>\n{content}\n</content_to_evaluate>"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    max_attempts = 2
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1024,
                "timeout": 30.0,
            }
            # If using Ollama, pass api_base
            if model.startswith("ollama/"):
                kwargs["api_base"] = os.environ.get(
                    "OLLAMA_API_BASE", "http://localhost:11434"
                )
            # Also use api_base from config if set
            elif hasattr(config, "api_base") and config.api_base:
                kwargs["api_base"] = config.api_base

            response = await litellm.acompletion(**kwargs)

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
            # Check if it's a timeout error - retry if attempts remain
            is_timeout = (
                isinstance(e, httpx.TimeoutException)
                or "timeout" in str(e).lower()
            )
            if is_timeout and attempt < max_attempts - 1:
                logger.warning(
                    "Timeout on attempt %d/%d, retrying in 1s: %s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
                await asyncio.sleep(1)
                continue
            logger.error("LLM API call failed: %s", e)
            break

    # All attempts failed — return low-confidence default
    logger.error(
        "All attempts to score content failed. Last error: %s", last_error
    )
    return _default_score_result(model)
