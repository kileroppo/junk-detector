"""Tests for src/core/token_roi.py — ROI computation and storage."""

import pytest

from src.core.token_roi import compute_roi, get_roi_stats, save_roi_record


class TestComputeRoi:
    """Tests for compute_roi function."""

    def test_basic_computation(self):
        """ROI = abs(llm_score - rules_score) / max(tokens_used, 1)."""
        roi = compute_roi(rules_score=40.0, llm_score=60.0, tokens_used=100)
        assert roi == pytest.approx(0.2, abs=1e-6)

    def test_zero_tokens(self):
        """Zero tokens should use 1 as denominator (avoid division by zero)."""
        roi = compute_roi(rules_score=40.0, llm_score=60.0, tokens_used=0)
        assert roi == pytest.approx(20.0, abs=1e-6)

    def test_negative_difference(self):
        """Should use absolute difference."""
        roi = compute_roi(rules_score=80.0, llm_score=60.0, tokens_used=100)
        assert roi == pytest.approx(0.2, abs=1e-6)

    def test_no_difference(self):
        """Same scores should yield zero ROI."""
        roi = compute_roi(rules_score=50.0, llm_score=50.0, tokens_used=500)
        assert roi == pytest.approx(0.0, abs=1e-6)

    def test_large_tokens(self):
        """Large token counts should yield small ROI."""
        roi = compute_roi(rules_score=40.0, llm_score=60.0, tokens_used=10000)
        assert roi == pytest.approx(0.002, abs=1e-6)


class TestSaveAndRetrieveRoi:
    """Tests for save_roi_record and get_roi_stats."""

    def test_save_and_get_stats(self, tmp_db_path):
        """Save records and verify stats retrieval."""
        save_roi_record(
            content_hash="abc123",
            tokens_used=100,
            rules_score=40.0,
            llm_score=60.0,
            roi=0.2,
            db_path=tmp_db_path,
        )
        save_roi_record(
            content_hash="def456",
            tokens_used=200,
            rules_score=50.0,
            llm_score=70.0,
            roi=0.1,
            db_path=tmp_db_path,
        )

        stats = get_roi_stats(db_path=tmp_db_path)
        assert stats["total_calls"] == 2
        assert stats["total_tokens"] == 300
        assert stats["avg_roi"] == pytest.approx(0.15, abs=0.01)
        assert stats["avg_info_gain"] == pytest.approx(20.0, abs=0.1)

    def test_get_stats_empty_db(self, tmp_db_path):
        """Empty database should return zeros."""
        stats = get_roi_stats(db_path=tmp_db_path)
        assert stats["avg_roi"] == 0.0
        assert stats["total_tokens"] == 0
        assert stats["total_calls"] == 0
        assert stats["avg_info_gain"] == 0.0

    def test_single_record(self, tmp_db_path):
        """Single record should return its own values."""
        save_roi_record(
            content_hash="single",
            tokens_used=500,
            rules_score=30.0,
            llm_score=80.0,
            roi=0.1,
            db_path=tmp_db_path,
        )

        stats = get_roi_stats(db_path=tmp_db_path)
        assert stats["total_calls"] == 1
        assert stats["total_tokens"] == 500
        assert stats["avg_roi"] == pytest.approx(0.1, abs=0.01)
        assert stats["avg_info_gain"] == pytest.approx(50.0, abs=0.1)
