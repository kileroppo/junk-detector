"""Tests for src/core/calibration.py - Scoring Calibration Module."""

from __future__ import annotations

import sqlite3

import pytest

from src.core.calibration import (
    _extract_distinctive_ngrams,
    _extract_ngrams,
    _score_to_verdict,
    get_calibration_stats,
    init_feedback_db,
    record_feedback,
    suggest_rule_updates,
)
from src.storage.db import init_db as init_scores_db


@pytest.fixture
def cal_db(tmp_db_path):
    """Initialize both scores and feedback tables."""
    init_scores_db(tmp_db_path)
    init_feedback_db(tmp_db_path)
    return tmp_db_path


def _insert_score(
    db_path: str, content_hash: str, overall_score: float, title: str = "Test"
) -> None:
    """Helper to insert a score record directly for testing."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO scores (
            input_type, source_url, title, content_hash, scored_at,
            overall_score, dimensions_json, labels_json, summary,
            model_used, cost, rule_hits_json, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "text",
            "https://example.com",
            title,
            content_hash,
            "2025-01-01T00:00:00",
            overall_score,
            "{}",
            "[]",
            "test summary",
            "test-model",
            0.0,
            "[]",
            1.0,
        ),
    )
    conn.commit()
    conn.close()


class TestInitFeedbackDb:
    """Tests for init_feedback_db."""

    def test_creates_feedback_table(self, tmp_db_path):
        """init_feedback_db creates the feedback table."""
        init_feedback_db(tmp_db_path)
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feedback'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_idempotent(self, tmp_db_path):
        """init_feedback_db can be called multiple times safely."""
        init_feedback_db(tmp_db_path)
        init_feedback_db(tmp_db_path)
        # No exception means success

    def test_feedback_table_schema(self, tmp_db_path):
        """Feedback table has expected columns."""
        init_feedback_db(tmp_db_path)
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.execute("PRAGMA table_info(feedback)")
        columns = {row[1] for row in cursor.fetchall()}
        assert columns == {"id", "content_hash", "user_verdict", "created_at", "content_text", "original_score"}
        conn.close()


class TestRecordFeedback:
    """Tests for record_feedback."""

    def test_stores_feedback_correctly(self, cal_db):
        """record_feedback stores the feedback in the database."""
        record_feedback("hash123", "junk", cal_db)

        conn = sqlite3.connect(cal_db)
        cursor = conn.execute("SELECT * FROM feedback WHERE content_hash = 'hash123'")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[1] == "hash123"  # content_hash
        assert row[2] == "junk"  # user_verdict

    def test_stores_all_verdict_types(self, cal_db):
        """record_feedback accepts all valid verdict types."""
        record_feedback("hash1", "junk", cal_db)
        record_feedback("hash2", "ok", cal_db)
        record_feedback("hash3", "excellent", cal_db)

        conn = sqlite3.connect(cal_db)
        cursor = conn.execute("SELECT COUNT(*) FROM feedback")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 3

    def test_invalid_verdict_raises(self, cal_db):
        """record_feedback raises ValueError for invalid verdict."""
        with pytest.raises(ValueError, match="Invalid verdict"):
            record_feedback("hash1", "bad_verdict", cal_db)

    def test_multiple_feedback_same_hash(self, cal_db):
        """Multiple feedback entries can be recorded for same content_hash."""
        record_feedback("hash1", "junk", cal_db)
        record_feedback("hash1", "ok", cal_db)

        conn = sqlite3.connect(cal_db)
        cursor = conn.execute("SELECT COUNT(*) FROM feedback WHERE content_hash = 'hash1'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 2

    def test_stores_created_at_timestamp(self, cal_db):
        """record_feedback stores a created_at timestamp."""
        record_feedback("hash1", "junk", cal_db)

        conn = sqlite3.connect(cal_db)
        cursor = conn.execute("SELECT created_at FROM feedback WHERE content_hash = 'hash1'")
        row = cursor.fetchone()
        conn.close()

        assert row[0] is not None
        assert "T" in row[0]  # ISO format contains T

    def test_lazy_init(self, tmp_db_path):
        """record_feedback initializes the DB lazily if not already initialized."""
        # Don't call init_feedback_db first
        record_feedback("hash1", "ok", tmp_db_path)

        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM feedback")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1


class TestScoreToVerdict:
    """Tests for _score_to_verdict."""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0, "junk"),
            (10, "junk"),
            (39, "junk"),
            (39.9, "junk"),
            (40, "ok"),
            (55, "ok"),
            (70, "ok"),
            (70.1, "excellent"),
            (85, "excellent"),
            (100, "excellent"),
        ],
    )
    def test_score_mapping(self, score, expected):
        """_score_to_verdict correctly maps scores to verdicts."""
        assert _score_to_verdict(score) == expected


class TestGetCalibrationStats:
    """Tests for get_calibration_stats."""

    def test_empty_db(self, cal_db):
        """Returns zero stats on empty database."""
        stats = get_calibration_stats(cal_db)
        assert stats["total_feedback_count"] == 0
        assert stats["agreement_rate"] == 0.0
        assert stats["false_positives"] == 0
        assert stats["false_negatives"] == 0

    def test_all_agree(self, cal_db):
        """100% agreement when all verdicts match."""
        # Score 30 -> predicted "junk", user says "junk"
        _insert_score(cal_db, "hash1", 30.0)
        record_feedback("hash1", "junk", cal_db)

        # Score 55 -> predicted "ok", user says "ok"
        _insert_score(cal_db, "hash2", 55.0)
        record_feedback("hash2", "ok", cal_db)

        # Score 85 -> predicted "excellent", user says "excellent"
        _insert_score(cal_db, "hash3", 85.0)
        record_feedback("hash3", "excellent", cal_db)

        stats = get_calibration_stats(cal_db)
        assert stats["total_feedback_count"] == 3
        assert stats["agreement_rate"] == 100.0
        assert stats["false_positives"] == 0
        assert stats["false_negatives"] == 0

    def test_all_disagree(self, cal_db):
        """0% agreement when all verdicts differ."""
        # Score 30 -> predicted "junk", user says "excellent"
        _insert_score(cal_db, "hash1", 30.0)
        record_feedback("hash1", "excellent", cal_db)

        # Score 85 -> predicted "excellent", user says "junk"
        _insert_score(cal_db, "hash2", 85.0)
        record_feedback("hash2", "junk", cal_db)

        stats = get_calibration_stats(cal_db)
        assert stats["total_feedback_count"] == 2
        assert stats["agreement_rate"] == 0.0
        assert stats["false_positives"] == 1
        assert stats["false_negatives"] == 1

    def test_mixed_results(self, cal_db):
        """Correct stats with mixed agreement/disagreement."""
        # Agreement: score 20 (junk), user says junk
        _insert_score(cal_db, "hash1", 20.0)
        record_feedback("hash1", "junk", cal_db)

        # Agreement: score 80 (excellent), user says excellent
        _insert_score(cal_db, "hash2", 80.0)
        record_feedback("hash2", "excellent", cal_db)

        # False positive: score 20 (junk), user says ok
        _insert_score(cal_db, "hash3", 20.0)
        record_feedback("hash3", "ok", cal_db)

        # False negative: score 60 (ok), user says junk
        _insert_score(cal_db, "hash4", 60.0)
        record_feedback("hash4", "junk", cal_db)

        stats = get_calibration_stats(cal_db)
        assert stats["total_feedback_count"] == 4
        assert stats["agreement_rate"] == 50.0
        assert stats["false_positives"] == 1
        assert stats["false_negatives"] == 1

    def test_feedback_without_score_ignored(self, cal_db):
        """Feedback entries without matching score records are not counted."""
        # Only feedback, no score record
        record_feedback("no_score_hash", "junk", cal_db)

        stats = get_calibration_stats(cal_db)
        assert stats["total_feedback_count"] == 0

    def test_boundary_scores(self, cal_db):
        """Tests boundary values for score-to-verdict mapping."""
        # Score exactly 40 -> "ok"
        _insert_score(cal_db, "hash1", 40.0)
        record_feedback("hash1", "ok", cal_db)

        # Score exactly 70 -> "ok"
        _insert_score(cal_db, "hash2", 70.0)
        record_feedback("hash2", "ok", cal_db)

        stats = get_calibration_stats(cal_db)
        assert stats["total_feedback_count"] == 2
        assert stats["agreement_rate"] == 100.0

    def test_lazy_init(self, tmp_db_path):
        """get_calibration_stats initializes the DB lazily."""
        init_scores_db(tmp_db_path)
        stats = get_calibration_stats(tmp_db_path)
        assert stats["total_feedback_count"] == 0


class TestSuggestRuleUpdates:
    """Tests for suggest_rule_updates."""

    def test_empty_db(self, cal_db):
        """Returns empty suggestions on empty database."""
        result = suggest_rule_updates(cal_db)
        assert result["suggested_keywords"] == []
        assert result["suggested_removals"] == []

    def test_identifies_false_negative_keywords(self, cal_db):
        """Suggests keywords from false negative content."""
        # False negatives: scored as ok/excellent but user says junk
        # Using repeated Chinese text in titles to meet min_frequency
        _insert_score(cal_db, "hash1", 75.0, title="免费领取大额优惠券")
        record_feedback("hash1", "junk", cal_db)

        _insert_score(cal_db, "hash2", 80.0, title="免费领取专属福利")
        record_feedback("hash2", "junk", cal_db)

        _insert_score(cal_db, "hash3", 65.0, title="正常的技术文章讨论")
        record_feedback("hash3", "ok", cal_db)

        result = suggest_rule_updates(cal_db)
        # "免费领取" should appear as a suggestion (appears in both false negatives)
        assert "免费领取" in result["suggested_keywords"]

    def test_identifies_false_positive_removals(self, cal_db):
        """Suggests removals from false positive content."""
        # False positives: scored as junk but user says ok/excellent
        _insert_score(cal_db, "hash1", 20.0, title="深度学习框架对比分析")
        record_feedback("hash1", "excellent", cal_db)

        _insert_score(cal_db, "hash2", 25.0, title="深度学习入门指南")
        record_feedback("hash2", "ok", cal_db)

        result = suggest_rule_updates(cal_db)
        # "深度学习" should appear as a removal suggestion
        assert "深度学习" in result["suggested_removals"]

    def test_no_false_negatives(self, cal_db):
        """No suggestions when there are no false negatives."""
        # All correct
        _insert_score(cal_db, "hash1", 30.0, title="垃圾内容")
        record_feedback("hash1", "junk", cal_db)

        _insert_score(cal_db, "hash2", 80.0, title="好文章")
        record_feedback("hash2", "excellent", cal_db)

        result = suggest_rule_updates(cal_db)
        assert result["suggested_keywords"] == []

    def test_filters_out_baseline_ngrams(self, cal_db):
        """Suggested keywords do not include n-grams from true positives."""
        # True positive (correctly identified as ok)
        _insert_score(cal_db, "hash1", 55.0, title="技术分析报告发布")
        record_feedback("hash1", "ok", cal_db)

        # False negative with overlapping text
        _insert_score(cal_db, "hash2", 75.0, title="技术分析报告骗局")
        record_feedback("hash2", "junk", cal_db)

        _insert_score(cal_db, "hash3", 80.0, title="最新技术分析报告骗局")
        record_feedback("hash3", "junk", cal_db)

        result = suggest_rule_updates(cal_db)
        # "技术分析" appears in both target and baseline, should be excluded
        assert "技术分析" not in result["suggested_keywords"]


class TestExtractNgrams:
    """Tests for _extract_ngrams helper."""

    def test_basic_chinese_text(self):
        """Extracts n-grams from Chinese text."""
        ngrams = _extract_ngrams("你好世界")
        # 2-grams: 你好, 好世, 世界
        # 3-grams: 你好世, 好世界
        # 4-grams: 你好世界
        assert "你好" in ngrams
        assert "好世" in ngrams
        assert "世界" in ngrams
        assert "你好世" in ngrams
        assert "好世界" in ngrams
        assert "你好世界" in ngrams

    def test_ignores_pure_ascii_ngrams(self):
        """Does not include n-grams that are purely ASCII."""
        ngrams = _extract_ngrams("hello")
        assert ngrams == []

    def test_mixed_text(self):
        """Handles mixed Chinese and ASCII text."""
        ngrams = _extract_ngrams("AI技术")
        # Should include n-grams that have at least one CJK character
        assert any("技" in ng for ng in ngrams)

    def test_empty_text(self):
        """Returns empty list for empty text."""
        assert _extract_ngrams("") == []

    def test_short_text(self):
        """Returns empty list for text shorter than min_n."""
        assert _extract_ngrams("你") == []


class TestExtractDistinctiveNgrams:
    """Tests for _extract_distinctive_ngrams helper."""

    def test_empty_target(self):
        """Returns empty list when no target texts."""
        result = _extract_distinctive_ngrams([], ["some text"])
        assert result == []

    def test_empty_baseline(self):
        """Returns frequent n-grams when baseline is empty."""
        result = _extract_distinctive_ngrams(["免费领取", "免费领取"], [], min_frequency=2)
        assert "免费领取" in result

    def test_filters_baseline_ngrams(self):
        """Excludes n-grams that appear in baseline."""
        result = _extract_distinctive_ngrams(
            ["免费领取优惠", "免费领取优惠"],
            ["免费领取正品"],
            min_frequency=2,
        )
        # "免费领取" appears in baseline, should not be suggested
        assert "免费领取" not in result

    def test_respects_min_frequency(self):
        """Only includes n-grams meeting minimum frequency."""
        result = _extract_distinctive_ngrams(
            ["独特词语"],  # Only appears once
            [],
            min_frequency=2,
        )
        assert result == []

    def test_top_k_limit(self):
        """Respects the top_k limit."""
        # Create enough unique n-grams
        texts = ["测试词语" * 5] * 3
        result = _extract_distinctive_ngrams(texts, [], top_k=3, min_frequency=2)
        assert len(result) <= 3
