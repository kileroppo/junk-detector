"""Tests for src/core/adaptive_prompt.py — adaptive prompt generation."""

from src.core.adaptive_prompt import ALL_DIMENSIONS, build_adaptive_prompt


class TestBuildAdaptivePrompt:
    """Tests for the build_adaptive_prompt function."""

    def test_full_prompt_for_all_9_dimensions(self):
        """When all 9 dimensions are requested, should return the full system prompt."""
        result = build_adaptive_prompt(ALL_DIMENSIONS, language="zh")
        # The full system prompt includes all dimension descriptions
        assert "originality" in result
        assert "scam_prob" in result
        assert "info_density" in result
        # Should be the full prompt loaded from file
        assert "内容质量评估专家" in result

    def test_shorter_prompt_for_partial_dims(self):
        """Fewer dimensions should produce a shorter prompt."""
        full_prompt = build_adaptive_prompt(ALL_DIMENSIONS, language="zh")
        partial_prompt = build_adaptive_prompt(["scam_prob", "advertorial_prob"], language="zh")
        # The partial prompt should be shorter
        assert len(partial_prompt) < len(full_prompt)

    def test_partial_prompt_contains_requested_dims(self):
        """Partial prompt should describe only the requested dimensions."""
        dims = ["scam_prob", "originality", "emotional_manipulation"]
        result = build_adaptive_prompt(dims, language="zh")
        assert "scam_prob" in result
        assert "originality" in result
        assert "emotional_manipulation" in result

    def test_partial_prompt_excludes_unrequested_dims(self):
        """Partial prompt should not describe dimensions not requested."""
        dims = ["scam_prob"]
        result = build_adaptive_prompt(dims, language="zh")
        # Should not have descriptions for unrequested dims
        assert "info_density (0-100)" not in result
        assert "readability (0-100)" not in result

    def test_output_format_instructions_present(self):
        """Partial prompt should include JSON output format instructions."""
        dims = ["scam_prob", "originality"]
        result = build_adaptive_prompt(dims, language="zh")
        assert "json" in result.lower() or "JSON" in result
        assert "confidence" in result
        assert "summary" in result

    def test_english_language(self):
        """English prompts should use English descriptions."""
        dims = ["scam_prob", "originality"]
        result = build_adaptive_prompt(dims, language="en")
        assert "content quality evaluation expert" in result.lower() or "Evaluate" in result
        assert "scam_prob" in result

    def test_full_prompt_english(self):
        """Full prompt in English should be the full system prompt."""
        result = build_adaptive_prompt(ALL_DIMENSIONS, language="en")
        # Should load from the en system prompt file (falls back to zh if not found)
        assert "originality" in result

    def test_positive_and_negative_sections(self):
        """Prompt should separate positive and negative dimensions."""
        dims = ["originality", "scam_prob"]
        result = build_adaptive_prompt(dims, language="zh")
        assert "正面维度" in result
        assert "负面维度" in result

    def test_only_negative_dims(self):
        """Prompt with only negative dims should not have positive section."""
        dims = ["scam_prob", "advertorial_prob"]
        result = build_adaptive_prompt(dims, language="zh")
        assert "负面维度" in result
        # Should not include positive section header
        assert "正面维度" not in result
