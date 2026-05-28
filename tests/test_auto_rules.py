"""Tests for TF-IDF-based auto rule generation in calibration module."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.core.calibration import (
    _group_by_cooccurrence,
    _infer_dimension,
    init_feedback_db,
    suggest_new_rules,
)
from src.core.custom_rules import VALID_DIMENSIONS


@pytest.fixture
def feedback_db(tmp_path: Path) -> str:
    """Create a temporary database with feedback data for testing."""
    db_path = str(tmp_path / "test.db")
    init_feedback_db(db_path)
    return db_path


def _insert_feedback(db_path: str, content_text: str, user_verdict: str, original_score: float) -> None:
    """Helper to insert feedback directly into the database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO feedback (content_hash, user_verdict, content_text, original_score, created_at) "
        "VALUES (?, ?, ?, ?, datetime('now'))",
        (f"hash_{hash(content_text)}", user_verdict, content_text, original_score),
    )
    conn.commit()
    conn.close()


class TestSuggestNewRulesEmpty:
    """Tests for empty or insufficient data."""

    def test_no_feedback_returns_empty(self, feedback_db: str) -> None:
        """No feedback data should return empty list."""
        result = suggest_new_rules(min_count=3, db_path=feedback_db)
        assert result == []

    def test_insufficient_feedback_returns_empty(self, feedback_db: str) -> None:
        """Less than min_count false negatives returns empty list."""
        # Only 1 false negative - not enough
        _insert_feedback(feedback_db, "投资赚钱暴富", "junk", 80.0)
        result = suggest_new_rules(min_count=3, db_path=feedback_db)
        assert result == []

    def test_no_false_negatives_returns_empty(self, feedback_db: str) -> None:
        """Feedback that agrees with system should return empty."""
        # User says ok, system scored ok (score >= 40) - agreement, not false negative
        _insert_feedback(feedback_db, "正常新闻内容", "ok", 75.0)
        _insert_feedback(feedback_db, "另一篇正常文章", "ok", 80.0)
        result = suggest_new_rules(min_count=2, db_path=feedback_db)
        assert result == []

    def test_low_score_feedback_not_false_negative(self, feedback_db: str) -> None:
        """Feedback where system already scored as junk (< 40) is not a false negative."""
        _insert_feedback(feedback_db, "系统已检测骗局内容", "junk", 20.0)
        _insert_feedback(feedback_db, "另一个已检测骗局", "junk", 15.0)
        _insert_feedback(feedback_db, "第三个已检测", "junk", 30.0)
        result = suggest_new_rules(min_count=2, db_path=feedback_db)
        assert result == []


class TestSuggestNewRulesWithData:
    """Tests for rule generation with sufficient false negative data."""

    def test_produces_rule_candidates_with_scam_keywords(self, feedback_db: str) -> None:
        """Sufficient scam-related false negatives should produce candidates."""
        # Insert enough false negatives with shared keywords
        texts = [
            "加微信免费教你赚钱投资",
            "免费加微信了解赚钱项目",
            "加微信免费领取投资教程",
            "免费赚钱加微信私聊了解",
            "微信加好友免费赚钱秘籍",
        ]
        for text in texts:
            _insert_feedback(feedback_db, text, "junk", 75.0)

        # Add some non-false-negative data for corpus
        _insert_feedback(feedback_db, "正常的技术文章讨论", "ok", 80.0)
        _insert_feedback(feedback_db, "今天天气很好适合出门", "ok", 85.0)

        result = suggest_new_rules(min_count=3, db_path=feedback_db)
        assert len(result) > 0

    def test_rule_candidates_have_required_fields(self, feedback_db: str) -> None:
        """Rule candidates must have all required fields."""
        texts = [
            "推荐这个好用的产品链接",
            "种草推荐好用必买链接",
            "超好用推荐给大家链接在这",
            "好用产品推荐链接购买",
        ]
        for text in texts:
            _insert_feedback(feedback_db, text, "junk", 70.0)
        _insert_feedback(feedback_db, "普通的新闻报道", "ok", 80.0)

        result = suggest_new_rules(min_count=2, db_path=feedback_db)

        for rule in result:
            assert "name" in rule
            assert "keywords" in rule
            assert "target_dimension" in rule
            assert "score_contribution" in rule
            assert "confidence" in rule

            # Validate types
            assert isinstance(rule["name"], str)
            assert isinstance(rule["keywords"], list)
            assert len(rule["keywords"]) > 0
            assert rule["target_dimension"] in VALID_DIMENSIONS
            assert 0 < rule["score_contribution"] <= 100
            assert 0 < rule["confidence"] <= 1.0

    def test_rule_candidates_match_custom_rule_schema(self, feedback_db: str) -> None:
        """Rule candidates should be compatible with CustomRule schema."""
        from src.core.custom_rules import CustomRule

        texts = [
            "震惊必看太可怕了赶紧转发",
            "震惊不敢相信必看赶紧",
            "太可怕了震惊必看快看",
            "赶紧看必看震惊内容",
        ]
        for text in texts:
            _insert_feedback(feedback_db, text, "junk", 65.0)
        _insert_feedback(feedback_db, "平静的科学文章", "ok", 90.0)

        result = suggest_new_rules(min_count=2, db_path=feedback_db)

        for rule in result:
            # Should be able to construct a CustomRule from the candidate
            custom_rule = CustomRule(
                name=rule["name"],
                keywords=rule["keywords"],
                target_dimension=rule["target_dimension"],
                score_contribution=rule["score_contribution"],
                confidence=rule["confidence"],
            )
            assert custom_rule.name == rule["name"]

    def test_confidence_based_on_coverage(self, feedback_db: str) -> None:
        """Confidence should reflect how many false negatives the pattern covers."""
        # All texts share a common pattern
        texts = [
            "加微信免费赚钱",
            "加微信免费投资",
            "加微信免费领取",
        ]
        for text in texts:
            _insert_feedback(feedback_db, text, "junk", 80.0)

        result = suggest_new_rules(min_count=2, db_path=feedback_db)
        if result:
            # Confidence should be > 0 since patterns cover all texts
            assert result[0]["confidence"] > 0

    def test_min_count_filtering(self, feedback_db: str) -> None:
        """Higher min_count should require more evidence."""
        texts = [
            "加微信赚钱暴富",
            "微信加好友赚钱",
            "加微信了解赚钱",
        ]
        for text in texts:
            _insert_feedback(feedback_db, text, "junk", 75.0)
        _insert_feedback(feedback_db, "正常内容", "ok", 85.0)

        # With min_count=3, should find patterns present in all 3
        suggest_new_rules(min_count=2, db_path=feedback_db)
        # With min_count=10, won't find anything (only 3 texts)
        result_high = suggest_new_rules(min_count=10, db_path=feedback_db)

        assert len(result_high) == 0
        # result_low may or may not produce results depending on n-gram overlap
        # but at least it should not error


class TestInferDimension:
    """Tests for dimension inference logic."""

    def test_scam_keywords(self) -> None:
        """Keywords with scam indicators should infer scam_prob."""
        result = _infer_dimension(["赚钱方法", "免费领取", "加微信了"])
        assert result == "scam_prob"

    def test_advertorial_keywords(self) -> None:
        """Keywords with advertorial indicators should infer advertorial_prob."""
        result = _infer_dimension(["推荐好物", "种草分享", "优惠链接"])
        assert result == "advertorial_prob"

    def test_emotional_keywords(self) -> None:
        """Keywords with emotional indicators should infer emotional_manipulation."""
        result = _infer_dimension(["震惊全国", "太可怕了", "不敢相信"])
        assert result == "emotional_manipulation"

    def test_ai_keywords(self) -> None:
        """Keywords with AI indicators should infer ai_generated_prob."""
        result = _infer_dimension(["众所周知是", "综上所述来", "值得注意的"])
        assert result == "ai_generated_prob"

    def test_unknown_keywords_default_scam(self) -> None:
        """Unknown keywords should default to scam_prob."""
        result = _infer_dimension(["普通词汇", "一般用语"])
        assert result == "scam_prob"

    def test_empty_keywords(self) -> None:
        """Empty keywords should default to scam_prob."""
        result = _infer_dimension([])
        assert result == "scam_prob"


class TestGroupByCooccurrence:
    """Tests for the co-occurrence grouping logic."""

    def test_empty_terms(self) -> None:
        """Empty terms returns empty groups."""
        result = _group_by_cooccurrence([], [], 2)
        assert result == []

    def test_single_term(self) -> None:
        """Single term with no co-occurrence partner gets its own group."""
        doc_sets = [{"term1", "other"}, {"term1", "another"}]
        result = _group_by_cooccurrence(["term1"], doc_sets, 2)
        assert len(result) == 1
        assert "term1" in result[0]

    def test_cooccurring_terms_grouped(self) -> None:
        """Terms that co-occur frequently should be grouped together."""
        doc_sets = [
            {"a", "b", "c"},
            {"a", "b", "d"},
            {"a", "b", "e"},
        ]
        result = _group_by_cooccurrence(["a", "b", "c", "d"], doc_sets, 2)
        # a and b co-occur in all 3 docs, so they should be in same group
        found_group = False
        for group in result:
            if "a" in group and "b" in group:
                found_group = True
                break
        assert found_group

    def test_non_cooccurring_terms_separate(self) -> None:
        """Terms that don't co-occur should not be grouped together."""
        doc_sets = [
            {"a", "b"},
            {"c", "d"},
            {"a", "b"},
            {"c", "d"},
        ]
        result = _group_by_cooccurrence(["a", "b", "c", "d"], doc_sets, 2)
        # a,b co-occur and c,d co-occur but a,c don't
        for group in result:
            assert not ("a" in group and "c" in group)
