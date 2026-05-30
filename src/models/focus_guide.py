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
    preview: str = Field(default="", description="Opening words so reader can locate this section")
    search_anchor: str = Field(
        default="", description="Short unique substring for copy-to-search in original"
    )
    why_read: str = Field(default="", description="Content-specific reason this paragraph matters")
    position_label: str = Field(default="", description="Human position: 开篇/前部/中部/后部/结尾")
    position_percent: int = Field(default=0, ge=0, le=100, description="Approximate position in article")
    density_score: float = Field(default=0.0, ge=0, le=1, description="Internal ranking score")


class SkippableSection(BaseModel):
    """Consecutive low-value paragraphs grouped for readable skip advice."""

    start_index: int = Field(..., description="First paragraph index in group (0-based)")
    end_index: int = Field(..., description="Last paragraph index in group (inclusive)")
    preview: str = Field(default="", description="Opening words of the skippable block")
    search_anchor: str = Field(default="", description="Unique search substring for this block")
    reason: str = Field(default="套话堆砌，缺乏实质信息")
    evidence: list[str] = Field(
        default_factory=list, description="Matched phrases from this paragraph"
    )
    position_label: str = Field(default="")
    position_percent: int = Field(default=0, ge=0, le=100)
    headline: str = Field(default="", description="Short title, e.g. 套话堆叠区")
    skip_advice: str = Field(default="", description="Actionable skip guidance for the reader")
    pattern_type: str = Field(
        default="low_density",
        description="filler | transition | water | vague | low_density",
    )
    paragraph_count: int = Field(default=1, ge=1, description="Number of paragraphs in this block")


class ReadingCaution(BaseModel):
    """Single 'don't trust blindly' warning for the reader."""

    headline: str = Field(..., description="Short warning title")
    message: str = Field(..., description="Why to be skeptical")
    preview: str = Field(default="", description="Representative excerpt")
    search_anchor: str = Field(default="")
    index: Optional[int] = Field(default=None, description="Paragraph index in original text")


class ParagraphSnippet(BaseModel):
    """Excerpt shown in the inline original-text panel."""

    index: int
    text: str
    status: str = Field(description="gold | skip | caution")
    search_anchor: str = ""
    label: str = Field(default="", description="Must-read / Skippable / Caution")


class FocusGuide(BaseModel):
    """Focus Guide for AI-generated content analysis."""

    recommendation: str = Field(
        ..., description="Overall reading recommendation: skip/skim/read_carefully"
    )
    verdict_headline: str = Field(default="", description="One-line reading decision")
    verdict_detail: str = Field(default="", description="Supporting sentence for the verdict")
    top_nuggets: list[InformationNugget] = Field(
        default_factory=list, description="Up to 3 must-read paragraphs"
    )
    caution: Optional[ReadingCaution] = Field(
        default=None, description="Single skepticism warning"
    )
    snippets: list[ParagraphSnippet] = Field(
        default_factory=list, description="Inline original excerpts for context"
    )
    suspicious_paragraphs: list[SuspiciousParagraph] = Field(default_factory=list)
    ai_patterns: list[AIPattern] = Field(default_factory=list)
    tldr: str = Field(default="", description="2-3 sentence actual content summary")
    empty_calorie_indices: list[int] = Field(
        default_factory=list, description="Paragraph indices with no real info"
    )
    information_nuggets: list[InformationNugget] = Field(default_factory=list)
    skippable_sections: list[SkippableSection] = Field(
        default_factory=list, description="Grouped skippable blocks with previews"
    )
    paragraph_count: int = Field(default=0, ge=0, description="Total paragraphs analyzed")
    reading_map: list[str] = Field(
        default_factory=list,
        description="Per-paragraph status: gold | skip | neutral (for visual map)",
    )
    reading_time_saved_percent: int = Field(
        default=0, ge=0, le=100, description="Estimated % of content skippable"
    )
    rhythm_fingerprint: Optional[RhythmFingerprintModel] = Field(
        default=None, description="Writing rhythm analysis data"
    )
