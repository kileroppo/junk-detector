"""Tests for src/core/embeddings.py — embedding and similarity functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.embeddings import cosine_similarity, embed_content


class TestCosineSimilarity:
    """Tests for cosine_similarity."""

    def test_identical_vectors(self):
        """Identical vectors have similarity 1.0."""
        vec = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors have similarity 0.0."""
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Opposite vectors have similarity -1.0."""
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)

    def test_empty_vector_returns_zero(self):
        """Empty vector returns 0.0."""
        assert cosine_similarity([], [1.0, 2.0]) == 0.0
        assert cosine_similarity([1.0, 2.0], []) == 0.0

    def test_dimension_mismatch_returns_zero(self):
        """Vectors of different dimensions return 0.0."""
        assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0

    def test_zero_magnitude_returns_zero(self):
        """Zero vector returns 0.0."""
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_similar_vectors(self):
        """Similar vectors have high similarity."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [1.1, 2.1, 3.1]
        sim = cosine_similarity(vec_a, vec_b)
        assert sim > 0.99


class TestEmbedContent:
    """Tests for embed_content."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self):
        """embed_content with empty text returns empty list."""
        result = await embed_content("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_embedding(self):
        """embed_content returns embedding from litellm."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

        with patch("litellm.aembedding", new_callable=AsyncMock, return_value=mock_response):
            result = await embed_content("Test text")
            assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self):
        """embed_content returns empty list on failure."""
        with patch(
            "litellm.aembedding", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            result = await embed_content("Test text")
            assert result == []

    @pytest.mark.asyncio
    async def test_passes_api_base(self):
        """embed_content passes api_base when provided."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.5]}]

        with patch(
            "litellm.aembedding", new_callable=AsyncMock, return_value=mock_response
        ) as mock_embed:
            await embed_content("Text", api_base="http://localhost:11434")
            call_kwargs = mock_embed.call_args[1]
            assert call_kwargs["api_base"] == "http://localhost:11434"
