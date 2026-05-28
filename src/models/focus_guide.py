"""Pydantic models for Focus Guide (重点关注指南) feature."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RhythmFingerprintModel(BaseModel):
    """Writing rhythm fingerprint data for template display."""

    rhythm_uniformity: float = Field(..., ge=0, le=100)
    sentence_diversity: float = Field(..., ge=0, le=100)
    topic_drift: float = Field(..., ge=0, le=100)
    paragraph_count: int = Field(default=0, ge=0)
    avg_paragraph_length: float = Field(default=0.0, ge=0)
    length_std_dev: float = Field(default=0.0, ge=0)


class SuspiciousParagraph(BaseModel):
    """A paragraph flagged as likely AI-generated."""

    index: int = Field(..., description="Paragraph index (0-based)")
    reason: str = Field(..., description="Why this paragraph is suspicious")
    severity: str = Field(default="medium", description="low/medium/high")


class AIPattern(BaseModel):
    """A detected AI-generation pattern."""

    pattern_name: str = Field(..., description="Name of the detected pattern")
    description: str = Field(..., description="Human-readable explanation")
    examples: list[str] = Field(default_factory=list, description="Excerpts showing this pattern")


class InformationNugget(BaseModel):
    """A paragraph containing genuinely useful information."""

    index: int = Field(..., description="Paragraph index")
    summary: str = Field(..., description="What useful info this paragraph contains")


class FocusGuide(BaseModel):
    """Focus Guide for AI-generated content analysis."""

    recommendation: str = Field(
        ..., description="Overall reading recommendation: skip/skim/read_carefully"
    )
    suspicious_paragraphs: list[SuspiciousParagraph] = Field(default_factory=list)
    ai_patterns: list[AIPattern] = Field(default_factory=list)
    tldr: str = Field(default="", description="2-3 sentence actual content summary")
    empty_calorie_indices: list[int] = Field(
        default_factory=list, description="Paragraph indices with no real info"
    )
    information_nuggets: list[InformationNugget] = Field(default_factory=list)
    reading_time_saved_percent: int = Field(
        default=0, ge=0, le=100, description="Estimated % of content skippable"
    )
    rhythm_fingerprint: Optional[RhythmFingerprintModel] = Field(
        default=None, description="Writing rhythm analysis data"
    )
