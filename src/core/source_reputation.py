"""Source reputation system — blacklist/whitelist management.

Inspired by x-algorithm's Author Diversity Scorer which attenuates
repeated low-quality sources.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


def _find_config_file(config_path: str | None = None) -> Path | None:
    """Find config.yaml using the same logic as src.core.config."""
    if config_path:
        p = Path(config_path)
        if p.exists():
            return p
        return None

    # Try cwd first
    cwd_config = Path.cwd() / "config.yaml"
    if cwd_config.exists():
        return cwd_config

    # Try project root (relative to this file)
    project_root = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    if project_root.exists():
        return project_root

    return None


def _load_sources_config(config_path: str | None = None) -> dict[str, Any]:
    """Load the 'sources' section from config.yaml."""
    path = _find_config_file(config_path)
    if path is None:
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return {}

    return data.get("sources", {})


def _normalize_domain(domain: str) -> str:
    """Normalize a domain string: lowercase, strip www. prefix."""
    domain = domain.strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def load_source_lists(config_path: str | None = None) -> tuple[set[str], set[str]]:
    """Load blacklist and whitelist from config.yaml.

    Returns (blacklist_set, whitelist_set) of normalized domain strings.
    """
    sources = _load_sources_config(config_path)

    blacklist_raw = sources.get("blacklist", [])
    whitelist_raw = sources.get("whitelist", [])

    blacklist = {_normalize_domain(d) for d in blacklist_raw if d}
    whitelist = {_normalize_domain(d) for d in whitelist_raw if d}

    return blacklist, whitelist


def is_blacklisted(domain: str, config_path: str | None = None) -> bool:
    """Check if a domain is blacklisted."""
    blacklist, _ = load_source_lists(config_path)
    return _normalize_domain(domain) in blacklist


def is_whitelisted(domain: str, config_path: str | None = None) -> bool:
    """Check if a domain is whitelisted."""
    _, whitelist = load_source_lists(config_path)
    return _normalize_domain(domain) in whitelist


def check_auto_blacklist(domain: str, db_path: str = "junk_detector.db", config_path: str | None = None) -> bool:
    """Check if a domain should be auto-blacklisted based on historical scores.

    Returns True if domain qualifies for auto-blacklisting:
    - Has at least min_articles scored articles
    - Average score is at or below max_avg_score

    Does NOT modify config.yaml — this is a runtime check only.
    """
    from src.storage.db import query as db_query

    sources = _load_sources_config(config_path)
    auto_config = sources.get("auto_blacklist", {})

    if not auto_config.get("enabled", False):
        return False

    min_articles = auto_config.get("min_articles", 5)
    max_avg_score = auto_config.get("max_avg_score", 30)

    normalized = _normalize_domain(domain)
    if not normalized:
        return False

    # Query all scores and filter by domain
    try:
        all_scores = db_query(filters=None, limit=1000, db_path=db_path)

        domain_scores = []
        for record in all_scores:
            record_url = record.get("source_url", "")
            if not record_url:
                continue
            try:
                record_domain = urlparse(record_url).netloc.lower()
                if record_domain.startswith("www."):
                    record_domain = record_domain[4:]
                if record_domain == normalized:
                    domain_scores.append(record["overall_score"])
            except Exception:
                continue

        if len(domain_scores) >= min_articles:
            avg_score = sum(domain_scores) / len(domain_scores)
            return avg_score <= max_avg_score

    except Exception as e:
        logger.warning(f"Auto-blacklist check failed for {domain}: {e}")

    return False


def get_source_adjustment(
    domain: str | None,
    config_path: str | None = None,
    db_path: str = "junk_detector.db",
) -> tuple[float, str]:
    """Get the score adjustment for a given domain.

    Returns (adjustment_amount, reason_string):
    - Blacklisted: (-penalty, "来源已列入黑名单")
    - Auto-blacklisted: (-20, "来源历史评分极低")
    - Whitelisted: (+boost, "可信来源")
    - Normal: (0, "")
    """
    if not domain:
        return (0, "")

    normalized = _normalize_domain(domain)
    if not normalized:
        return (0, "")

    sources = _load_sources_config(config_path)
    blacklist_penalty = sources.get("blacklist_penalty", 30)
    whitelist_boost = sources.get("whitelist_boost", 5)

    # Check explicit blacklist first (highest priority)
    blacklist, whitelist = load_source_lists(config_path)

    if normalized in blacklist:
        return (-blacklist_penalty, "来源已列入黑名单")

    # Check auto-blacklist
    if check_auto_blacklist(normalized, db_path=db_path, config_path=config_path):
        return (-20, "来源历史评分极低")

    # Check whitelist
    if normalized in whitelist:
        return (whitelist_boost, "可信来源")

    return (0, "")
