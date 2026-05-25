"""Content Fingerprinting — SimHash for fast plagiarism detection.

Inspired by x-algorithm's Hash Embedding pattern.
Produces compact 64-bit fingerprints for text content.
Similar texts have low Hamming distance between fingerprints.

Zero API cost, runs in microseconds.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger("fingerprint")

_FINGERPRINT_BITS = 64


@dataclass
class FingerprintMatch:
    """A match found between two content fingerprints."""

    content_hash: str  # hash of the matching article
    title: str | None
    source_url: str | None
    hamming_distance: int  # 0 = identical, lower = more similar
    similarity: float  # 1.0 = identical, higher = more similar


def simhash(text: str) -> int:
    """Compute SimHash fingerprint for text content.

    Algorithm:
    1. Tokenize text into shingles (n-grams)
    2. Hash each shingle to a 64-bit value
    3. For each bit position: sum +1 if bit is 1, -1 if bit is 0
    4. Final hash: bit is 1 if sum > 0, else 0

    Args:
        text: Text content to fingerprint.

    Returns:
        64-bit integer fingerprint.
    """
    # Tokenize into 3-char shingles (works for both Chinese and English)
    tokens = _tokenize(text)

    if not tokens:
        return 0

    # Compute weighted bit vector
    v = [0] * _FINGERPRINT_BITS

    for token in tokens:
        # Hash the token to get a 64-bit value
        token_hash = _hash_token(token)

        for i in range(_FINGERPRINT_BITS):
            bit = (token_hash >> i) & 1
            if bit:
                v[i] += 1
            else:
                v[i] -= 1

    # Convert to fingerprint
    fingerprint = 0
    for i in range(_FINGERPRINT_BITS):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def hamming_distance(fp1: int, fp2: int) -> int:
    """Compute Hamming distance between two fingerprints.

    Args:
        fp1: First 64-bit fingerprint.
        fp2: Second 64-bit fingerprint.

    Returns:
        Number of differing bits (0 = identical, max = 64).
    """
    xor = fp1 ^ fp2
    return bin(xor).count("1")


def similarity_score(fp1: int, fp2: int) -> float:
    """Compute similarity score between two fingerprints.

    Args:
        fp1: First fingerprint.
        fp2: Second fingerprint.

    Returns:
        Similarity from 0.0 (completely different) to 1.0 (identical).
    """
    distance = hamming_distance(fp1, fp2)
    return 1.0 - (distance / _FINGERPRINT_BITS)


def find_similar(
    text: str,
    threshold: int = 5,
    db_path: str = "junk_detector.db",
) -> list[FingerprintMatch]:
    """Find articles with similar fingerprints in the database.

    Args:
        text: Text to check for similarity.
        threshold: Maximum Hamming distance to consider a match (default 5).
        db_path: Path to the SQLite database.

    Returns:
        List of FingerprintMatch objects, sorted by distance (most similar first).
    """
    fp = simhash(text)

    # Load stored fingerprints
    stored = _load_fingerprints(db_path)

    matches = []
    for stored_fp, content_hash, title, source_url in stored:
        distance = hamming_distance(fp, stored_fp)
        if distance <= threshold:
            matches.append(
                FingerprintMatch(
                    content_hash=content_hash,
                    title=title,
                    source_url=source_url,
                    hamming_distance=distance,
                    similarity=similarity_score(fp, stored_fp),
                )
            )

    # Sort by distance (most similar first)
    matches.sort(key=lambda m: m.hamming_distance)
    return matches


def save_fingerprint(
    text: str,
    content_hash: str,
    title: str | None = None,
    source_url: str | None = None,
    db_path: str = "junk_detector.db",
) -> int:
    """Compute and save a fingerprint to the database.

    Args:
        text: Content text.
        content_hash: Unique content hash (from Content model).
        title: Article title.
        source_url: Article source URL.
        db_path: Path to the SQLite database.

    Returns:
        The computed fingerprint integer.
    """
    fp = simhash(text)
    _ensure_table(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO content_fingerprints
            (content_hash, fingerprint, title, source_url)
            VALUES (?, ?, ?, ?)
            """,
            (content_hash, _to_signed(fp), title, source_url),
        )
        conn.commit()
    finally:
        conn.close()

    return fp


# --- Internal helpers ---


def _tokenize(text: str) -> list[str]:
    """Tokenize text into overlapping 3-character shingles.

    Works for both Chinese (character-level) and English (word-level + char).
    """
    # Clean text
    text = re.sub(r"\s+", " ", text.strip().lower())

    if len(text) < 3:
        return [text] if text else []

    # Generate 3-char shingles
    shingles = []
    for i in range(len(text) - 2):
        shingles.append(text[i : i + 3])

    return shingles


def _hash_token(token: str) -> int:
    """Hash a token to a 64-bit integer using MD5."""
    digest = hashlib.md5(token.encode()).digest()
    # Use first 8 bytes as 64-bit int
    return int.from_bytes(digest[:8], byteorder="little")


def _to_signed(fp: int) -> int:
    """Convert unsigned 64-bit int to signed for SQLite storage."""
    if fp >= (1 << 63):
        return fp - (1 << 64)
    return fp


def _to_unsigned(fp: int) -> int:
    """Convert signed 64-bit int from SQLite back to unsigned."""
    if fp < 0:
        return fp + (1 << 64)
    return fp


_initialized_dbs: set[str] = set()

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS content_fingerprints (
    content_hash TEXT PRIMARY KEY,
    fingerprint INTEGER NOT NULL,
    title TEXT,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_table(db_path: str) -> None:
    """Create fingerprints table if not exists."""
    if db_path in _initialized_dbs:
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        _initialized_dbs.add(db_path)
    finally:
        conn.close()


def _load_fingerprints(db_path: str) -> list[tuple[int, str, str | None, str | None]]:
    """Load all stored fingerprints from database."""
    _ensure_table(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT fingerprint, content_hash, title, source_url FROM content_fingerprints"
        )
        return [(_to_unsigned(row[0]), row[1], row[2], row[3]) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_stats(db_path: str = "junk_detector.db") -> dict:
    """Get fingerprint database statistics."""
    _ensure_table(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM content_fingerprints")
        count = cursor.fetchone()[0]
        return {"total_fingerprints": count}
    finally:
        conn.close()
