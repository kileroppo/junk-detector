"""Writing rhythm fingerprint analysis.

Analyzes the structural rhythm of text to detect AI-generated patterns:
- Paragraph length uniformity (AI tends to produce very even paragraphs)
- Sentence length diversity (humans vary sentence length more)
- Topic drift (AI often stays on-topic with little vocabulary shift)
"""

from __future__ import annotations

import re
import statistics

from pydantic import BaseModel, Field


class RhythmFingerprint(BaseModel):
    """Quantified writing rhythm characteristics."""

    rhythm_uniformity: float = Field(
        ..., ge=0, le=100, description="0-100, higher = more robotic/uniform paragraph lengths"
    )
    sentence_diversity: float = Field(
        ..., ge=0, le=100, description="0-100, higher = more diverse sentence lengths"
    )
    topic_drift: float = Field(
        ..., ge=0, le=100, description="0-100, higher = more vocabulary shift between paragraphs"
    )
    paragraph_count: int = Field(..., ge=0, description="Number of paragraphs analyzed")
    avg_paragraph_length: float = Field(..., ge=0, description="Mean paragraph character count")
    length_std_dev: float = Field(..., ge=0, description="Std dev of paragraph lengths")


def _split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs."""
    return [p.strip() for p in text.split("\n") if p.strip()]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (handles Chinese and English punctuation)."""
    parts = re.split(r"[。！？.!?]+", text)
    return [s.strip() for s in parts if s.strip()]


def _compute_rhythm_uniformity(paragraphs: list[str]) -> float:
    """Compute rhythm uniformity score (0-100).

    Based on coefficient of variation (std_dev / mean) of paragraph lengths.
    Low CV means highly uniform (robotic) -> high score.
    """
    if len(paragraphs) < 2:
        return 50.0  # Not enough data, return neutral

    lengths = [len(p) for p in paragraphs]
    mean_len = statistics.mean(lengths)

    if mean_len == 0:
        return 50.0

    std_dev = statistics.stdev(lengths)
    cv = std_dev / mean_len

    # Map CV to uniformity score:
    # cv < 0.2 -> ~90 (very uniform, likely AI)
    # cv ~ 0.35 -> ~50 (medium)
    # cv > 0.5 -> ~20 (very diverse, likely human)
    if cv < 0.1:
        return 95.0
    elif cv < 0.2:
        # Linear interpolation: cv 0.1->95, cv 0.2->75
        return 95.0 - (cv - 0.1) * 200.0
    elif cv < 0.35:
        # cv 0.2->75, cv 0.35->50
        return 75.0 - (cv - 0.2) * (25.0 / 0.15)
    elif cv < 0.5:
        # cv 0.35->50, cv 0.5->20
        return 50.0 - (cv - 0.35) * (30.0 / 0.15)
    else:
        # cv >= 0.5 -> clamp between 5 and 20
        return max(5.0, 20.0 - (cv - 0.5) * 30.0)


def _compute_sentence_diversity(paragraphs: list[str]) -> float:
    """Compute sentence length diversity score (0-100).

    High coefficient of variation of sentence lengths = high diversity (good, human-like).
    """
    all_sentences = []
    for para in paragraphs:
        all_sentences.extend(_split_sentences(para))

    if len(all_sentences) < 3:
        return 50.0  # Not enough data

    lengths = [len(s) for s in all_sentences]
    mean_len = statistics.mean(lengths)

    if mean_len == 0:
        return 50.0

    std_dev = statistics.stdev(lengths)
    cv = std_dev / mean_len

    # High CV means diverse sentence lengths (human-like) -> high score
    # cv > 0.6 -> ~85 (very diverse)
    # cv ~ 0.3 -> ~50 (medium)
    # cv < 0.15 -> ~20 (very uniform, AI-like)
    if cv >= 0.6:
        return min(95.0, 85.0 + (cv - 0.6) * 25.0)
    elif cv >= 0.3:
        # cv 0.3->50, cv 0.6->85
        return 50.0 + (cv - 0.3) * (35.0 / 0.3)
    elif cv >= 0.15:
        # cv 0.15->25, cv 0.3->50
        return 25.0 + (cv - 0.15) * (25.0 / 0.15)
    else:
        return max(5.0, 25.0 - (0.15 - cv) * 133.0)


def _compute_topic_drift(paragraphs: list[str]) -> float:
    """Compute topic drift score (0-100).

    Measures average Jaccard distance between consecutive paragraph character sets.
    High distance = more varied topics (higher drift score).
    """
    if len(paragraphs) < 2:
        return 50.0  # Not enough data

    distances = []
    for i in range(len(paragraphs) - 1):
        # Use character n-grams (bigrams) for vocabulary comparison
        set_a = set(paragraphs[i][j : j + 2] for j in range(len(paragraphs[i]) - 1))
        set_b = set(paragraphs[i + 1][j : j + 2] for j in range(len(paragraphs[i + 1]) - 1))

        if not set_a and not set_b:
            continue

        # Jaccard distance = 1 - (intersection / union)
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        if union == 0:
            continue

        distance = 1.0 - (intersection / union)
        distances.append(distance)

    if not distances:
        return 50.0

    avg_distance = statistics.mean(distances)

    # Map avg_distance to score:
    # distance ~ 0.2 -> low drift (AI repeats similar vocab) -> score ~25
    # distance ~ 0.4 -> medium drift -> score ~50
    # distance ~ 0.7 -> high drift (human varied topics) -> score ~80
    score = avg_distance * 100.0
    return max(0.0, min(100.0, score))


def analyze_rhythm(text: str) -> RhythmFingerprint:
    """Analyze the writing rhythm of a text.

    Args:
        text: The content text to analyze.

    Returns:
        RhythmFingerprint with computed metrics.
    """
    paragraphs = _split_paragraphs(text)

    if not paragraphs:
        return RhythmFingerprint(
            rhythm_uniformity=50.0,
            sentence_diversity=50.0,
            topic_drift=50.0,
            paragraph_count=0,
            avg_paragraph_length=0.0,
            length_std_dev=0.0,
        )

    lengths = [len(p) for p in paragraphs]
    avg_len = statistics.mean(lengths)
    std_dev = statistics.stdev(lengths) if len(lengths) > 1 else 0.0

    rhythm_uniformity = _compute_rhythm_uniformity(paragraphs)
    sentence_diversity = _compute_sentence_diversity(paragraphs)
    topic_drift = _compute_topic_drift(paragraphs)

    return RhythmFingerprint(
        rhythm_uniformity=round(rhythm_uniformity, 1),
        sentence_diversity=round(sentence_diversity, 1),
        topic_drift=round(topic_drift, 1),
        paragraph_count=len(paragraphs),
        avg_paragraph_length=round(avg_len, 1),
        length_std_dev=round(std_dev, 1),
    )
