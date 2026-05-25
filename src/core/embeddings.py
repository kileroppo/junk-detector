"""Content embedding and similarity detection for junk-detector.

Inspired by Phoenix's two-tower retrieval model (x-algorithm):
- Phoenix uses User Tower + Candidate Tower embeddings with dot-product similarity
- We simplify: embed article text → store embedding → compare against stored
  embeddings → flag potential copies if similarity > threshold

This enables detection of plagiarism/洗稿/搬运 (content laundering/reposting).
"""

from __future__ import annotations

import math
import logging

logger = logging.getLogger(__name__)


async def embed_content(
    text: str,
    model: str = "ollama/nomic-embed-text",
    api_base: str | None = None,
) -> list[float]:
    """Embed article text into a vector using litellm.

    Args:
        text: The article text to embed.
        model: Embedding model identifier. Defaults to local Ollama model.
               Use "text-embedding-3-small" for OpenAI.
        api_base: Optional API base URL (e.g., for local Ollama instance).

    Returns:
        Embedding vector as a list of floats.
        Returns empty list on failure (graceful degradation).
    """
    import litellm

    # Truncate to first 8000 chars (embedding model context limit)
    truncated_text = text[:8000]

    if not truncated_text.strip():
        logger.warning("embed_content called with empty text, returning empty vector")
        return []

    try:
        kwargs: dict = {
            "model": model,
            "input": [truncated_text],
        }
        if api_base:
            kwargs["api_base"] = api_base

        response = await litellm.aembedding(**kwargs)
        embedding = response.data[0]["embedding"]
        return embedding
    except Exception as e:
        logger.warning(f"Embedding failed (model={model}): {e}")
        return []


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Pure Python implementation — no numpy dependency required.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Cosine similarity score in range [-1, 1].
        Returns 0.0 if either vector is empty or has zero magnitude.
    """
    if not vec_a or not vec_b:
        return 0.0

    if len(vec_a) != len(vec_b):
        logger.warning(
            f"Vector dimension mismatch: {len(vec_a)} vs {len(vec_b)}"
        )
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)
