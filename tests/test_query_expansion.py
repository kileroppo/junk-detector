"""Tests for src/core/query_expansion.py - keyword expansion with LLM."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.core.query_expansion import (
    _cache_key,
    _load_cache,
    _save_cache,
    expand_keywords,
)


class TestExpandKeywords:
    """Tests for the expand_keywords function."""

    @pytest.mark.asyncio
    async def test_expand_with_mocked_llm(self):
        """expand_keywords returns variants when LLM responds correctly."""
        mock_response = json.dumps({
            "日入过万": ["日赚万元", "每日收入过万", "日入w+"],
            "加微信": ["加v", "加wx", "加VX"],
        })

        with patch(
            "src.core.query_expansion._call_llm",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await expand_keywords(["日入过万", "加微信"], use_cache=False)

        assert "日入过万" in result
        assert "加微信" in result
        assert len(result["日入过万"]) >= 2
        assert len(result["加微信"]) >= 2

    @pytest.mark.asyncio
    async def test_expand_empty_keywords(self):
        """expand_keywords with empty list returns empty dict."""
        result = await expand_keywords([], use_cache=False)
        assert result == {}

    @pytest.mark.asyncio
    async def test_expand_llm_failure_returns_empty(self):
        """expand_keywords returns empty dict on LLM failure."""
        with patch(
            "src.core.query_expansion._call_llm",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await expand_keywords(["日入过万"], use_cache=False)
        assert result == {}

    @pytest.mark.asyncio
    async def test_expand_invalid_json_returns_empty(self):
        """expand_keywords returns empty dict on invalid JSON response."""
        with patch(
            "src.core.query_expansion._call_llm",
            new_callable=AsyncMock,
            return_value="This is not JSON at all",
        ):
            result = await expand_keywords(["日入过万"], use_cache=False)
        assert result == {}

    @pytest.mark.asyncio
    async def test_expand_non_dict_response_returns_empty(self):
        """expand_keywords returns empty dict when LLM returns non-dict JSON."""
        with patch(
            "src.core.query_expansion._call_llm",
            new_callable=AsyncMock,
            return_value='["not", "a", "dict"]',
        ):
            result = await expand_keywords(["日入过万"], use_cache=False)
        assert result == {}

    @pytest.mark.asyncio
    async def test_expand_uses_cache(self, tmp_path):
        """expand_keywords uses cached results on second call."""
        cache_file = tmp_path / "expansions.json"
        cached_data = {
            _cache_key(["test_kw"]): {"test_kw": ["variant1", "variant2"]},
        }
        cache_file.write_text(json.dumps(cached_data), encoding="utf-8")

        with (
            patch("src.core.query_expansion._CACHE_DIR", tmp_path),
            patch("src.core.query_expansion._CACHE_FILE", cache_file),
        ):
            result = await expand_keywords(["test_kw"], use_cache=True)

        assert result == {"test_kw": ["variant1", "variant2"]}


class TestCache:
    """Tests for expansion cache functions."""

    def test_cache_key_deterministic(self):
        """Same keywords produce same cache key."""
        key1 = _cache_key(["a", "b"])
        key2 = _cache_key(["a", "b"])
        assert key1 == key2

    def test_cache_key_order_independent(self):
        """Keywords in different order produce same key (sorted internally)."""
        key1 = _cache_key(["b", "a"])
        key2 = _cache_key(["a", "b"])
        assert key1 == key2

    def test_save_and_load_cache(self, tmp_path):
        """Cache round-trips correctly."""
        with (
            patch("src.core.query_expansion._CACHE_DIR", tmp_path),
            patch("src.core.query_expansion._CACHE_FILE", tmp_path / "expansions.json"),
        ):
            data = {"test": ["v1", "v2"]}
            _save_cache(data)
            loaded = _load_cache()
            assert loaded == data

    def test_load_cache_missing_file(self, tmp_path):
        """Loading from non-existent file returns empty dict."""
        with (
            patch("src.core.query_expansion._CACHE_DIR", tmp_path),
            patch("src.core.query_expansion._CACHE_FILE", tmp_path / "nonexistent.json"),
        ):
            loaded = _load_cache()
            assert loaded == {}

    def test_load_cache_invalid_json(self, tmp_path):
        """Loading from corrupt file returns empty dict."""
        bad_file = tmp_path / "expansions.json"
        bad_file.write_text("not json", encoding="utf-8")
        with (
            patch("src.core.query_expansion._CACHE_DIR", tmp_path),
            patch("src.core.query_expansion._CACHE_FILE", bad_file),
        ):
            loaded = _load_cache()
            assert loaded == {}
