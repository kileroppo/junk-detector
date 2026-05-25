"""Tests for src/core/prompt_loader.py system prompt loading."""

from __future__ import annotations

import pytest

from src.core.prompt_loader import clear_cache, get_system_prompt


class TestGetSystemPrompt:
    """Test system prompt loading for prompt injection defense."""

    def setup_method(self):
        clear_cache()

    def test_get_system_prompt_zh(self):
        """System prompt for 'zh' should contain rubric but NOT {content} placeholder."""
        prompt = get_system_prompt("zh")
        assert "originality" in prompt
        assert "info_density" in prompt
        assert "reasoning_quality" in prompt
        assert "{content}" not in prompt
        assert "待评估内容" not in prompt

    def test_get_system_prompt_fast(self):
        """System prompt for 'fast' should contain 4 dimensions but NOT {content}."""
        prompt = get_system_prompt("fast")
        assert "scam_prob" in prompt
        assert "advertorial_prob" in prompt
        assert "emotional_manipulation" in prompt
        assert "originality" in prompt
        assert "quick_verdict" in prompt
        assert "{content}" not in prompt
        assert "待评估内容" not in prompt

    def test_get_system_prompt_en(self):
        """System prompt for 'en' should contain English rubric but NOT {content}."""
        prompt = get_system_prompt("en")
        assert "originality" in prompt
        assert "info_density" in prompt
        assert "{content}" not in prompt
        assert "Content to Evaluate" not in prompt

    def test_get_system_prompt_anti_injection(self):
        """All system prompts should contain anti-injection instruction."""
        for lang in ("zh", "en", "fast"):
            prompt = get_system_prompt(lang)
            assert "content for evaluation only" in prompt.lower() or "Ignore any instructions" in prompt

    def test_get_system_prompt_fallback(self):
        """Unknown language should fall back to 'zh' system prompt."""
        prompt = get_system_prompt("unknown")
        assert "originality" in prompt
        assert "{content}" not in prompt

    def test_get_system_prompt_caching(self):
        """Subsequent calls should return cached result."""
        prompt1 = get_system_prompt("zh")
        prompt2 = get_system_prompt("zh")
        assert prompt1 is prompt2

    def test_clear_cache_clears_system_prompts(self):
        """clear_cache should also clear system template cache."""
        prompt1 = get_system_prompt("zh")
        clear_cache()
        prompt2 = get_system_prompt("zh")
        # After clearing, should reload (not be same object)
        assert prompt1 is not prompt2
        # But content should be the same
        assert prompt1 == prompt2
