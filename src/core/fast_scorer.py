"""Fast scorer module -- lightweight 4-dimension content screening."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Optional

import httpx
import litellm

from src.core.prompt_loader import get_prompt_template, get_system_prompt
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

    def _clamp_score(val, name: str) -> float:
        val = float(val)
        if val < 0 or val > 100:
            logger.warning("Score %s out of range: %.1f, clamping to [0, 100]", name, val)
            return max(0.0, min(100.0, val))
        return val

    # Clamp confidence to [0, 1]
    confidence = float(data.get("confidence", 0.8))
    if confidence < 0 or confidence > 1:
        logger.warning("Confidence out of range: %.2f, clamping to [0, 1]", confidence)
        confidence = max(0.0, min(1.0, confidence))

    return FastScoreResult(
        quick_verdict=_clamp_score(data["quick_verdict"], "quick_verdict"),
        scam_prob=_clamp_score(data["scam_prob"], "scam_prob"),
        advertorial_prob=_clamp_score(data["advertorial_prob"], "advertorial_prob"),
        emotional_manipulation=_clamp_score(data["emotional_manipulation"], "emotional_manipulation"),
        originality=_clamp_score(data["originality"], "originality"),
        summary=data.get("summary", "快速评分完成"),
        confidence=confidence,
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
    max_retries: int = 1,
) -> FastScoreResult:
    """Score content using the fast 4-dimension screening prompt.

    Args:
        content_text: The text content to evaluate.
        config: Scoring configuration (contains model name, etc.).
                If None, uses default ScoringConfig.
        language: Language code (unused for fast mode, kept for API consistency).
        max_retries: Number of retry attempts for timeout errors.

    Returns:
        FastScoreResult with 4 dimension scores and quick_verdict.
    """
    if config is None:
        config = ScoringConfig()

    model = config.primary_model
    system_prompt = get_system_prompt("fast")
    user_content = f"<content_to_evaluate>\n{content_text}\n</content_to_evaluate>"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    max_attempts = 2
    loop_count = max(max_attempts, max_retries + 1)
    last_error: Exception | None = None

    for attempt in range(loop_count):
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
                loop_count,
                e,
            )
            continue

        except Exception as e:
            last_error = e
            # Check if it's a timeout error - retry if retries remain
            is_timeout = (
                isinstance(e, httpx.TimeoutException)
                or "timeout" in str(e).lower()
            )
            if is_timeout and attempt < max_retries:
                logger.warning(
                    "Timeout on attempt %d/%d, retrying in 1s: %s",
                    attempt + 1,
                    max_retries + 1,
                    e,
                )
                await asyncio.sleep(1)
                continue
            logger.error("LLM API call failed in fast scorer: %s", e)
            break

    # All attempts failed - return low-confidence default
    logger.error(
        "All attempts to fast-score content failed. Last error: %s", last_error
    )
    return _default_fast_result(model)
