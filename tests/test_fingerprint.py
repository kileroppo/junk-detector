"""Tests for content fingerprinting (src.core.content_fingerprint).

Verifies SimHash computation, Hamming distance, and database round-trip.
Uses tmp_path for isolated database tests.
"""

from __future__ import annotations

from src.core.content_fingerprint import (
    find_similar,
    hamming_distance,
    save_fingerprint,
    simhash,
    similarity_score,
)


class TestSimhash:
    """Tests for the simhash() function."""

    def test_identical_texts_produce_same_fingerprint(self):
        """Two identical texts should produce the exact same fingerprint."""
        text = "This is a sample text for fingerprinting purposes"
        fp1 = simhash(text)
        fp2 = simhash(text)
        assert fp1 == fp2

    def test_very_different_texts_have_high_distance(self):
        """Completely different texts should have high Hamming distance."""
        text_a = "人工智能技术在自然语言处理领域取得显著进展"
        text_b = "The quick brown fox jumps over the lazy dog repeatedly"
        fp_a = simhash(text_a)
        fp_b = simhash(text_b)
        distance = hamming_distance(fp_a, fp_b)
        # Very different texts should have distance > 10
        assert distance > 10

    def test_similar_texts_have_low_distance(self):
        """Texts with minor edits should produce similar fingerprints."""
        text_a = "人工智能技术在自然语言处理领域取得了显著进展和突破"
        text_b = "人工智能技术在自然语言处理领域取得了重大进展和突破"
        fp_a = simhash(text_a)
        fp_b = simhash(text_b)
        distance = hamming_distance(fp_a, fp_b)
        # Similar texts should have low distance (< 15)
        assert distance < 15

    def test_empty_text_returns_zero(self):
        """Empty text produces a zero fingerprint."""
        assert simhash("") == 0

    def test_short_text_produces_nonzero(self):
        """Even short text (>= 3 chars) produces a nonzero fingerprint."""
        fp = simhash("abc")
        assert fp != 0


class TestHammingDistance:
    """Tests for hamming_distance()."""

    def test_identical_fingerprints_have_zero_distance(self):
        """hamming_distance(x, x) should always be 0."""
        fp = simhash("Test content for distance check")
        assert hamming_distance(fp, fp) == 0

    def test_distance_is_symmetric(self):
        """hamming_distance(a, b) == hamming_distance(b, a)."""
        fp_a = simhash("Content A")
        fp_b = simhash("Content B completely different")
        assert hamming_distance(fp_a, fp_b) == hamming_distance(fp_b, fp_a)

    def test_max_distance_is_64(self):
        """Maximum possible distance between two 64-bit fingerprints is 64."""
        # All bits different
        distance = hamming_distance(0, (1 << 64) - 1)
        assert distance == 64


class TestSimilarityScore:
    """Tests for similarity_score()."""

    def test_identical_fingerprints_score_1(self):
        """Identical fingerprints have similarity score of 1.0."""
        fp = simhash("test text")
        assert similarity_score(fp, fp) == 1.0

    def test_score_ranges_between_0_and_1(self):
        """Similarity score is always in [0, 1]."""
        fp_a = simhash("text A about technology")
        fp_b = simhash("completely different text B about cooking")
        score = similarity_score(fp_a, fp_b)
        assert 0.0 <= score <= 1.0

    def test_all_bits_different_scores_0(self):
        """When all 64 bits differ, similarity should be 0."""
        assert similarity_score(0, (1 << 64) - 1) == 0.0


class TestSaveAndFindFingerprint:
    """Tests for save_fingerprint() and find_similar() round-trip."""

    def test_save_and_find_round_trip(self, tmp_db_path):
        """Saved fingerprint can be found via find_similar."""
        text = "This is a test article about machine learning and AI developments"
        save_fingerprint(
            text=text,
            content_hash="hash123",
            title="Test Article",
            source_url="https://example.com/test",
            db_path=tmp_db_path,
        )

        # Same text should find itself
        matches = find_similar(text, threshold=5, db_path=tmp_db_path)
        assert len(matches) >= 1
        assert matches[0].content_hash == "hash123"
        assert matches[0].hamming_distance == 0
