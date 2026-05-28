"""Scoring calibration module - tracks user feedback for continuous improvement."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Any

from src.storage.db import _get_connection

_CREATE_FEEDBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    user_verdict TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_initialized_feedback_dbs: set[str] = set()

VALID_VERDICTS = ("junk", "ok", "excellent")


def _ensure_initialized(db_path: str) -> None:
    """Lazy initialization: create feedback table if not already done for this db_path."""
    if db_path not in _initialized_feedback_dbs:
        init_feedback_db(db_path)


def init_feedback_db(db_path: str = "junk_detector.db") -> None:
    """Create the feedback table if it does not exist, and migrate schema if needed.

    Adds content_text and original_score columns if they are missing (v2 migration).
    Also handles legacy schemas where user_verdict may be named 'verdict'.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_FEEDBACK_TABLE_SQL)
        conn.commit()

        # V2 migration: add content_text and original_score columns if missing
        cursor = conn.execute("PRAGMA table_info(feedback)")
        existing_columns = {row["name"] for row in cursor.fetchall()}

        if "content_text" not in existing_columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN content_text TEXT")
            conn.commit()

        if "original_score" not in existing_columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN original_score REAL")
            conn.commit()

        # Handle legacy schema: if 'verdict' exists but 'user_verdict' doesn't
        if "user_verdict" not in existing_columns and "verdict" in existing_columns:
            conn.execute("ALTER TABLE feedback RENAME COLUMN verdict TO user_verdict")
            conn.commit()

        _initialized_feedback_dbs.add(db_path)
    finally:
        conn.close()


def record_feedback(
    content_hash: str, user_verdict: str, db_path: str = "junk_detector.db"
) -> None:
    """Record user feedback on a scored piece of content.

    Args:
        content_hash: The SHA256 hash of the content text.
        user_verdict: One of 'junk', 'ok', 'excellent'.
        db_path: Path to the SQLite database file.

    Raises:
        ValueError: If user_verdict is not a valid verdict.
    """
    if user_verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid verdict '{user_verdict}'. Must be one of: {VALID_VERDICTS}")

    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO feedback (content_hash, user_verdict, created_at) VALUES (?, ?, ?)",
            (content_hash, user_verdict, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _score_to_verdict(score: float) -> str:
    """Map a numeric score to a verdict category.

    Args:
        score: Overall score from 0-100.

    Returns:
        'junk' if score < 40, 'ok' if 40-70, 'excellent' if > 70.
    """
    if score < 40:
        return "junk"
    elif score <= 70:
        return "ok"
    else:
        return "excellent"


def get_calibration_stats(db_path: str = "junk_detector.db") -> dict[str, Any]:
    """Calculate calibration statistics by comparing user feedback with scores.

    Joins the feedback table with the scores table on content_hash to compare
    predicted verdict (from overall_score) with user_verdict.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary with:
        - total_feedback_count: Total number of feedback entries with matching scores
        - agreement_rate: Percentage where predicted verdict matches user verdict
        - false_positives: Count of items scored as junk but user said ok/excellent
        - false_negatives: Count of items scored as ok/excellent but user said junk
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        cursor = conn.execute(
            """
            SELECT f.user_verdict, s.overall_score
            FROM feedback f
            INNER JOIN scores s ON f.content_hash = s.content_hash
            """
        )
        rows = cursor.fetchall()

        total_count = len(rows)
        if total_count == 0:
            return {
                "total_feedback_count": 0,
                "agreement_rate": 0.0,
                "false_positives": 0,
                "false_negatives": 0,
            }

        agreements = 0
        false_positives = 0
        false_negatives = 0

        for row in rows:
            user_verdict = row["user_verdict"]
            predicted_verdict = _score_to_verdict(row["overall_score"])

            if predicted_verdict == user_verdict:
                agreements += 1
            elif predicted_verdict == "junk" and user_verdict in ("ok", "excellent"):
                false_positives += 1
            elif predicted_verdict in ("ok", "excellent") and user_verdict == "junk":
                false_negatives += 1

        agreement_rate = (agreements / total_count) * 100.0

        return {
            "total_feedback_count": total_count,
            "agreement_rate": agreement_rate,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        }
    finally:
        conn.close()


def suggest_rule_updates(db_path: str = "junk_detector.db") -> dict[str, list[str]]:
    """Analyze false negatives and false positives to suggest rule updates.

    False negatives: content user flagged as junk but we scored as ok/excellent.
    Extracts frequent Chinese character n-grams (2-4 chars) from false negative
    content that don't appear in true positive content.

    False positives: content we scored as junk but user said was ok/excellent.
    Suggests keywords from those items that may need removal.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Dictionary with:
        - suggested_keywords: List of frequent n-grams from false negatives
        - suggested_removals: List of frequent n-grams from false positives
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        # Get all feedback with score and content text
        cursor = conn.execute(
            """
            SELECT f.user_verdict, s.overall_score, s.title
            FROM feedback f
            INNER JOIN scores s ON f.content_hash = s.content_hash
            """
        )
        rows = cursor.fetchall()

        false_negative_texts: list[str] = []
        true_positive_texts: list[str] = []
        false_positive_texts: list[str] = []

        for row in rows:
            user_verdict = row["user_verdict"]
            predicted_verdict = _score_to_verdict(row["overall_score"])
            text = row["title"] or ""

            if predicted_verdict in ("ok", "excellent") and user_verdict == "junk":
                # False negative: we missed it, user says it's junk
                false_negative_texts.append(text)
            elif predicted_verdict == user_verdict and user_verdict != "junk":
                # True positive (content correctly identified as ok/excellent)
                true_positive_texts.append(text)
            elif predicted_verdict == "junk" and user_verdict in ("ok", "excellent"):
                # False positive: we said junk but user says it's fine
                false_positive_texts.append(text)

        suggested_keywords = _extract_distinctive_ngrams(false_negative_texts, true_positive_texts)
        suggested_removals = _extract_distinctive_ngrams(false_positive_texts, true_positive_texts)

        return {
            "suggested_keywords": suggested_keywords,
            "suggested_removals": suggested_removals,
        }
    finally:
        conn.close()


def _extract_ngrams(text: str, min_n: int = 2, max_n: int = 4) -> list[str]:
    """Extract Chinese character n-grams from text.

    Args:
        text: Input text string.
        min_n: Minimum n-gram length.
        max_n: Maximum n-gram length.

    Returns:
        List of n-gram strings.
    """
    ngrams = []
    for n in range(min_n, max_n + 1):
        for i in range(len(text) - n + 1):
            ngram = text[i : i + n]
            # Only include n-grams that contain at least one CJK character
            if any("\u4e00" <= ch <= "\u9fff" for ch in ngram):
                ngrams.append(ngram)
    return ngrams


def _extract_distinctive_ngrams(
    target_texts: list[str],
    baseline_texts: list[str],
    top_k: int = 10,
    min_frequency: int = 2,
) -> list[str]:
    """Extract n-grams frequent in target texts but not in baseline texts.

    Args:
        target_texts: Texts to extract distinctive n-grams from.
        baseline_texts: Texts to compare against (exclude common n-grams).
        top_k: Maximum number of suggestions to return.
        min_frequency: Minimum occurrences in target to be considered.

    Returns:
        List of distinctive n-gram strings sorted by frequency.
    """
    if not target_texts:
        return []

    # Count n-grams in target texts
    target_counter: Counter[str] = Counter()
    for text in target_texts:
        ngrams = _extract_ngrams(text)
        target_counter.update(ngrams)

    # Count n-grams in baseline texts
    baseline_set: set[str] = set()
    for text in baseline_texts:
        ngrams = _extract_ngrams(text)
        baseline_set.update(ngrams)

    # Filter: must appear at least min_frequency times in target
    # and not appear in baseline
    distinctive = [
        (ngram, count)
        for ngram, count in target_counter.items()
        if count >= min_frequency and ngram not in baseline_set
    ]

    # Sort by frequency descending
    distinctive.sort(key=lambda x: x[1], reverse=True)

    return [ngram for ngram, _ in distinctive[:top_k]]


def save_feedback_with_content(
    content_hash: str,
    content_text: str,
    user_verdict: str,
    original_score: float,
    db_path: str = "junk_detector.db",
) -> None:
    """Record user feedback along with the content text and original score.

    This stores the full content text alongside feedback for later pattern mining.

    Args:
        content_hash: The SHA256 hash of the content text.
        content_text: The actual text content.
        user_verdict: One of 'junk', 'ok', 'excellent'.
        original_score: The system's original score for this content.
        db_path: Path to the SQLite database file.

    Raises:
        ValueError: If user_verdict is not a valid verdict.
    """
    if user_verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid verdict '{user_verdict}'. Must be one of: {VALID_VERDICTS}")

    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO feedback (content_hash, user_verdict, content_text, original_score, created_at) VALUES (?, ?, ?, ?, ?)",
            (content_hash, user_verdict, content_text, original_score, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def suggest_new_rules(min_count: int = 3, db_path: str = "junk_detector.db") -> list[dict]:
    """Analyze false negatives using TF-IDF scoring to generate rule candidates.

    Uses TF-IDF-like scoring to find terms distinctive to false negatives
    (user said 'junk' but system scored as ok/excellent). Terms that appear
    frequently in false negatives but rarely across all scored content
    receive the highest scores.

    Args:
        min_count: Minimum number of false negative texts a pattern must appear in.
        db_path: Path to the SQLite database file.

    Returns:
        List of rule candidate dicts matching CustomRule schema with keys:
        - name: auto-generated rule name
        - keywords: list of high TF-IDF keywords
        - target_dimension: inferred dimension to target
        - score_contribution: scaled by TF-IDF score (0-100)
        - confidence: based on coverage of false negatives (0-1)
    """
    _ensure_initialized(db_path)

    conn = _get_connection(db_path)
    try:
        # Query false negatives: user said junk, but system said ok/excellent
        cursor = conn.execute(
            """
            SELECT content_text, original_score
            FROM feedback
            WHERE user_verdict = 'junk'
              AND content_text IS NOT NULL
              AND (original_score >= 40 OR original_score IS NULL)
            """
        )
        fn_rows = cursor.fetchall()

        if not fn_rows:
            return []

        # Query ALL feedback content for corpus document frequency
        cursor = conn.execute(
            """
            SELECT content_text
            FROM feedback
            WHERE content_text IS NOT NULL
            """
        )
        all_rows = cursor.fetchall()

        # Extract n-grams from each false negative text
        fn_texts: list[str] = []
        fn_ngram_sets: list[set[str]] = []
        for row in fn_rows:
            text = row["content_text"]
            if text:
                fn_texts.append(text)
                ngrams = set(_extract_ngrams(text, min_n=2, max_n=4))
                fn_ngram_sets.append(ngrams)

        if not fn_ngram_sets:
            return []

        # Calculate term frequency in false negatives (how many FN docs contain term)
        fn_doc_freq: Counter[str] = Counter()
        for ngram_set in fn_ngram_sets:
            for ngram in ngram_set:
                fn_doc_freq[ngram] += 1

        # Calculate document frequency across ALL scored content
        all_ngram_sets: list[set[str]] = []
        for row in all_rows:
            text = row["content_text"]
            if text:
                ngrams = set(_extract_ngrams(text, min_n=2, max_n=4))
                all_ngram_sets.append(ngrams)

        total_docs = len(all_ngram_sets) if all_ngram_sets else 1
        all_doc_freq: Counter[str] = Counter()
        for ngram_set in all_ngram_sets:
            for ngram in ngram_set:
                all_doc_freq[ngram] += 1

        # Calculate TF-IDF score for each term
        # tf = term frequency in false negatives (fraction of FN docs containing term)
        # idf = log(total_docs / df) where df = document frequency across all content

        total_fn = len(fn_ngram_sets)
        tfidf_scores: dict[str, float] = {}

        for term, fn_count in fn_doc_freq.items():
            if fn_count < min_count:
                continue
            tf = fn_count / total_fn
            df = all_doc_freq.get(term, 1)
            idf = math.log(total_docs / df) if df > 0 else 0
            tfidf_scores[term] = tf * idf

        if not tfidf_scores:
            return []

        # Sort by TF-IDF score descending
        sorted_terms = sorted(tfidf_scores.items(), key=lambda x: x[1], reverse=True)

        # Group high-scoring terms by co-occurrence patterns
        # Two terms co-occur if they appear together in >= min_count false negative texts
        top_terms = [term for term, _ in sorted_terms[:30]]
        groups = _group_by_cooccurrence(top_terms, fn_ngram_sets, min_count)

        if not groups:
            # Fall back: use top terms as a single group
            groups = [top_terms[:5]]

        # Generate rule candidates from groups
        rules: list[dict] = []
        rule_index = 0

        for group_keywords in groups:
            if not group_keywords:
                continue

            # Infer target dimension from keywords
            dimension = _infer_dimension(group_keywords)

            # Calculate coverage: fraction of false negatives containing any keyword
            coverage = 0
            for ngram_set in fn_ngram_sets:
                if any(kw in ngram_set for kw in group_keywords):
                    coverage += 1
            confidence = round(min(1.0, coverage / total_fn), 2)

            # Scale score_contribution by max TF-IDF score in group
            max_tfidf = max(tfidf_scores.get(kw, 0) for kw in group_keywords)
            # Normalize: map tfidf to 15-50 range for score_contribution
            score_contribution = round(min(50.0, max(15.0, max_tfidf * 100)), 1)

            # Generate name from the top keyword
            name_suffix = dimension.replace("_prob", "").replace("_", "")
            rules.append({
                "name": f"auto_rule_{rule_index:03d}_{name_suffix}",
                "keywords": group_keywords[:5],
                "target_dimension": dimension,
                "score_contribution": score_contribution,
                "confidence": confidence,
            })
            rule_index += 1

            if rule_index >= 5:
                break

        return rules
    finally:
        conn.close()


def _group_by_cooccurrence(
    terms: list[str],
    doc_sets: list[set[str]],
    min_count: int,
) -> list[list[str]]:
    """Group terms by co-occurrence in documents.

    Two terms are grouped together if they co-occur in at least min_count documents.
    Returns groups of co-occurring terms.

    Args:
        terms: List of candidate terms to group.
        doc_sets: List of document n-gram sets.
        min_count: Minimum co-occurrence count.

    Returns:
        List of term groups (each group is a list of co-occurring terms).
    """
    if not terms:
        return []

    # Build co-occurrence counts
    cooccurrence: Counter[tuple[str, str]] = Counter()
    for doc_set in doc_sets:
        present = [t for t in terms if t in doc_set]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                pair = (present[i], present[j]) if present[i] < present[j] else (present[j], present[i])
                cooccurrence[pair] += 1

    # Build adjacency from co-occurring pairs
    adjacency: dict[str, set[str]] = {t: set() for t in terms}
    for (t1, t2), count in cooccurrence.items():
        if count >= min_count:
            adjacency[t1].add(t2)
            adjacency[t2].add(t1)

    # Greedy grouping: start from highest-degree nodes
    used: set[str] = set()
    groups: list[list[str]] = []

    for term in terms:
        if term in used:
            continue
        neighbors = adjacency[term] - used
        if neighbors:
            group = [term] + sorted(neighbors)[:4]
            groups.append(group)
            used.update(group)
        elif not used:
            # First term with no co-occurrence partners - add as singleton
            groups.append([term])
            used.add(term)

    return groups


def _infer_dimension(keywords: list[str]) -> str:
    """Infer the target dimension based on keyword content.

    Checks for overlap with known indicator terms for each dimension.

    Args:
        keywords: List of keywords to classify.

    Returns:
        One of: scam_prob, advertorial_prob, emotional_manipulation, ai_generated_prob
    """
    scam_indicators = ["赚钱", "暴富", "免费", "中奖", "转账", "加微", "私聊", "投资", "收益", "翻倍"]
    advertorial_indicators = ["推荐", "好用", "种草", "链接", "优惠", "折扣", "下单", "购买", "代购"]
    emotional_indicators = ["震惊", "泪目", "崩溃", "太可怕", "不敢相信", "赶紧", "必看", "快看"]
    ai_indicators = ["众所周知", "综上所述", "值得注意", "需要指出", "不可否认"]

    scores = {
        "scam_prob": 0,
        "advertorial_prob": 0,
        "emotional_manipulation": 0,
        "ai_generated_prob": 0,
    }

    for kw in keywords:
        if any(ind in kw for ind in scam_indicators):
            scores["scam_prob"] += 1
        if any(ind in kw for ind in advertorial_indicators):
            scores["advertorial_prob"] += 1
        if any(ind in kw for ind in emotional_indicators):
            scores["emotional_manipulation"] += 1
        if any(ind in kw for ind in ai_indicators):
            scores["ai_generated_prob"] += 1

    # Return dimension with highest score, default to scam_prob
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "scam_prob"
    return best
