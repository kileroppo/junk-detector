"""Fast scorer module -- lightweight 4-dimension content screening."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import litellm

from src.core.prompt_loader import get_prompt_template
from src.models.score import FastScoreResult, ScoringConfig

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


def _build_fast_result(data: dict, model: str) -> FastScoreResult:
    """Convert parsed JSON dict into a FastScoreResult."""
    return FastScoreResult(
        quick_verdict=float(data["quick_verdict"]),
        scam_prob=float(data["scam_prob"]),
        advertorial_prob=float(data["advertorial_prob"]),
        emotional_manipulation=float(data["emotional_manipulation"]),
        originality=float(data["originality"]),
        summary=data.get("summary", "快速评分完成"),
        confidence=float(data.get("confidence", 0.8)),
        model_used=model,
    )


def _default_fast_result(model: str) -> FastScoreResult:
    """Return a low-confidence default when parsing completely fails."""
    return FastScoreResult(
        quick_verdict=50.0,
        scam_prob=50.0,
        advertorial_prob=50.0,
        emotional_manipulation=50.0,
        originality=50.0,
        summary="LLM响应解析失败，返回默认评分",
        confidence=0.1,
        model_used=model,
    )


async def score_fast(
    content_text: str,
    config: Optional[ScoringConfig] = None,
    language: str = "zh",
) -> FastScoreResult:
    """Score content using the fast 4-dimension screening prompt.

    Args:
        content_text: The text content to evaluate.
        config: Scoring configuration (contains model name, etc.).
                If None, uses default ScoringConfig.
        language: Language code (unused for fast mode, kept for API consistency).

    Returns:
        FastScoreResult with 4 dimension scores and quick_verdict.
    """
    if config is None:
        config = ScoringConfig()

    model = config.primary_model
    template = get_prompt_template("fast")
    prompt = template.replace("{content}", content_text)

    messages = [{"role": "user", "content": prompt}]

    max_attempts = 2
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 256,
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
            result = _build_fast_result(data, model)

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
                "Attempt %d/%d: Failed to parse fast score response: %s",
                attempt + 1,
                max_attempts,
                e,
            )
            continue

        except Exception as e:
            last_error = e
            logger.error("LLM API call failed in fast scorer: %s", e)
            break

    # All attempts failed - return low-confidence default
    logger.error(
        "All attempts to fast-score content failed. Last error: %s", last_error
    )
    return _default_fast_result(model)
