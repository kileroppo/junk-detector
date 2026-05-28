"""Tests for src/core/content_optimizer.py — smart content truncation."""

from src.core.content_optimizer import smart_truncate


class TestSmartTruncate:
    """Tests for the smart_truncate function."""

    def test_short_text_unchanged(self):
        """Text shorter than max_chars should be returned unchanged."""
        text = "This is a short text."
        result = smart_truncate(text, max_chars=1500)
        assert result == text

    def test_exactly_max_chars_unchanged(self):
        """Text exactly at max_chars should be returned unchanged."""
        text = "a" * 1500
        result = smart_truncate(text, max_chars=1500)
        assert result == text

    def test_long_text_truncated(self):
        """Text longer than max_chars should be truncated."""
        text = "x" * 5000
        result = smart_truncate(text, max_chars=1500)
        assert len(result) <= 1500

    def test_segments_present_in_output(self):
        """Output should contain parts from the beginning and end."""
        # Create distinctive text so we can verify segments
        text = "START" * 50 + "MIDDLE" * 500 + "END" * 50
        result = smart_truncate(text, max_chars=1500)
        # The first 200 chars should include "START"
        assert "START" in result
        # The last 200 chars should include "END"
        assert "END" in result

    def test_separator_present(self):
        """Output should contain the [...] separator."""
        text = "Hello world. " * 500
        result = smart_truncate(text, max_chars=1500)
        assert "[...]" in result

    def test_suspicious_paragraph_extraction(self):
        """The most suspicious paragraph should be included."""
        # Create text where one paragraph has scam keywords
        normal = "这是一篇普通的文章内容，讨论科技发展趋势。" * 20
        scam_para = "日入过万！躺赚财富自由！限时免费加微信领取！名额有限！稳赚不赔！"
        text = normal + "\n" + scam_para + "\n" + normal
        result = smart_truncate(text, max_chars=1500)
        # The scam paragraph should be prioritized
        assert "日入过万" in result or "躺赚" in result or "财富自由" in result

    def test_custom_max_chars(self):
        """Custom max_chars should be respected."""
        text = "a" * 3000
        result = smart_truncate(text, max_chars=500)
        assert len(result) <= 500

    def test_empty_text(self):
        """Empty text should be returned unchanged."""
        assert smart_truncate("") == ""

    def test_single_line_long_text(self):
        """Long text without newlines should still be truncated properly."""
        text = "word " * 1000  # ~5000 chars
        result = smart_truncate(text, max_chars=1500)
        assert len(result) <= 1500

    def test_deterministic_output(self):
        """Same input should always produce the same output (no randomness)."""
        text = "a" * 200 + "b" * 2000 + "c" * 200 + "d" * 2000 + "e" * 200
        results = [smart_truncate(text, max_chars=1500) for _ in range(10)]
        # All results should be identical
        assert all(r == results[0] for r in results)

    def test_deterministic_different_texts(self):
        """Different inputs produce different middle segments (seed varies)."""
        text_a = "alpha" * 1000
        text_b = "bravo" * 1000
        result_a = smart_truncate(text_a, max_chars=1500)
        result_b = smart_truncate(text_b, max_chars=1500)
        # They should differ (different content, different seed)
        assert result_a != result_b
