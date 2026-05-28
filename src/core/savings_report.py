"""Monthly savings report - quantifies value vs direct AI usage.

Calculates how much the system saved compared to directly asking AI every time,
by aggregating data from scoring_stats and token_roi tables.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection using the shared engine."""
    from src.storage.engine import get_db_connection

    return get_db_connection(db_path)


def get_savings_report(days: int = 30, db_path: str = "junk_detector.db") -> dict:
    """Calculate savings over the past N days.

    Queries scores table, scoring_stats table, and token_roi table to
    compute how much the optimization layers (rules, caching, truncation)
    have saved compared to naive LLM usage.

    Args:
        days: Number of days to look back.
        db_path: Path to the SQLite database file.

    Returns:
        Dict with savings metrics:
        - total_scores: total evaluations in the period
        - rules_only_count: evaluations that used zero LLM tokens
        - cached_count: evaluations served from cache
        - total_tokens_used: actual tokens spent
        - estimated_tokens_if_no_optimization: tokens without adaptive prompt + truncation
        - token_savings_percent: percentage saved
        - estimated_cost_saved_yuan: money saved (assuming 0.001 per 1K tokens for DeepSeek)
        - avg_response_time_ms: average response time (estimated)
        - estimated_time_if_manual: estimated time if user manually asked AI each time
        - time_saved_minutes: time saved
    """
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = _get_connection(db_path)
    try:
        # Get total scores in the period
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM scores WHERE DATE(scored_at) >= ?",
                (start_date,),
            )
            row = cursor.fetchone()
            total_scores = row[0] if row else 0
        except Exception:
            total_scores = 0

        # Get rules_only and llm counts from scoring_stats
        rules_only_count = 0
        llm_count = 0
        try:
            cursor = conn.execute(
                """
                SELECT
                    COALESCE(SUM(rules_only_count), 0) as total_rules,
                    COALESCE(SUM(llm_count), 0) as total_llm
                FROM scoring_stats
                WHERE date >= ?
                """,
                (start_date,),
            )
            row = cursor.fetchone()
            if row:
                rules_only_count = row[0] or 0
                llm_count = row[1] or 0
        except Exception:
            pass

        # Count cached results (model_used = 'cache')
        cached_count = 0
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM scores WHERE model_used = 'cache' AND DATE(scored_at) >= ?",
                (start_date,),
            )
            row = cursor.fetchone()
            cached_count = row[0] if row else 0
        except Exception:
            pass

        # Get token usage from token_roi table
        total_tokens_used = 0
        try:
            cursor = conn.execute(
                """
                SELECT COALESCE(SUM(tokens_used), 0)
                FROM token_roi
                WHERE DATE(created_at) >= ?
                """,
                (start_date,),
            )
            row = cursor.fetchone()
            total_tokens_used = row[0] if row else 0
        except Exception:
            pass

        # Estimate tokens if no optimization:
        # Without truncation/adaptive prompt, each article would use ~2000 tokens
        # (average article is ~1500 chars = ~1500 tokens input + ~500 output)
        tokens_per_naive_call = 2000
        estimated_tokens_if_no_optimization = total_scores * tokens_per_naive_call

        # Token savings
        tokens_saved = max(0, estimated_tokens_if_no_optimization - total_tokens_used)
        token_savings_percent = (
            round(tokens_saved / estimated_tokens_if_no_optimization * 100, 1)
            if estimated_tokens_if_no_optimization > 0
            else 0.0
        )

        # Cost saved (DeepSeek pricing: ~0.001 yuan per 1K tokens)
        cost_per_1k_tokens = 0.001
        estimated_cost_saved_yuan = round(tokens_saved / 1000 * cost_per_1k_tokens, 3)

        # Time estimation
        # Average response time for our system: ~2s per scored item (rules are instant)
        avg_response_time_ms = 2000 if total_scores > 0 else 0

        # If user manually asked AI each time: ~5s per article
        seconds_per_manual = 5
        estimated_time_if_manual = total_scores * seconds_per_manual

        # Our system: rules_only are instant (~0.1s), LLM calls ~2s, cached ~0.1s
        our_total_seconds = (
            rules_only_count * 0.1 + llm_count * 2.0 + cached_count * 0.1
        )
        time_saved_seconds = max(0, estimated_time_if_manual - our_total_seconds)
        time_saved_minutes = round(time_saved_seconds / 60, 1)

        return {
            "total_scores": total_scores,
            "rules_only_count": rules_only_count,
            "cached_count": cached_count,
            "total_tokens_used": total_tokens_used,
            "estimated_tokens_if_no_optimization": estimated_tokens_if_no_optimization,
            "token_savings_percent": token_savings_percent,
            "estimated_cost_saved_yuan": estimated_cost_saved_yuan,
            "avg_response_time_ms": avg_response_time_ms,
            "estimated_time_if_manual": estimated_time_if_manual,
            "time_saved_minutes": time_saved_minutes,
        }

    except Exception as e:
        logger.exception("Failed to generate savings report")
        return {
            "total_scores": 0,
            "rules_only_count": 0,
            "cached_count": 0,
            "total_tokens_used": 0,
            "estimated_tokens_if_no_optimization": 0,
            "token_savings_percent": 0.0,
            "estimated_cost_saved_yuan": 0.0,
            "avg_response_time_ms": 0,
            "estimated_time_if_manual": 0,
            "time_saved_minutes": 0.0,
        }
    finally:
        conn.close()
