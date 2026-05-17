"""Pydantic models for user preferences."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScoringWeights(BaseModel):
    """Per-user scoring weight overrides. None means 'use system default'."""

    originality: Optional[float] = None
    info_density: Optional[float] = None
    reasoning_quality: Optional[float] = None
    readability: Optional[float] = None
    timeliness: Optional[float] = None
    ai_generated_prob: Optional[float] = None
    emotional_manipulation: Optional[float] = None
    advertorial_prob: Optional[float] = None
    scam_prob: Optional[float] = None


class LabelThresholds(BaseModel):
    """Per-user label threshold overrides. None means 'use system default'."""

    ai_generated: Optional[float] = None
    emotional_manipulation: Optional[float] = None
    advertorial: Optional[float] = None
    scam: Optional[float] = None
    high_quality: Optional[float] = None
    info_dense: Optional[float] = None


class MonitoredSource(BaseModel):
    """A content source monitored for a specific user."""

    name: str
    type: Literal["rss", "webhook"]
    url: str
    poll_interval_seconds: int = 300
    priority: int = 5
    enabled: bool = True


class UserPreferences(BaseModel):
    """Complete user preferences profile."""

    user_id: int
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    label_thresholds: LabelThresholds = Field(default_factory=LabelThresholds)
    monitored_sources: list[MonitoredSource] = Field(default_factory=list)
    preferred_model: Optional[str] = None  # override active model
    confidence_threshold: Optional[float] = None
    language: str = "zh"  # prompt language preference
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PreferencesUpdate(BaseModel):
    """Partial update model for user preferences (PATCH). All fields optional."""

    scoring_weights: Optional[ScoringWeights] = None
    label_thresholds: Optional[LabelThresholds] = None
    monitored_sources: Optional[list[MonitoredSource]] = None
    preferred_model: Optional[str] = None
    confidence_threshold: Optional[float] = None
    language: Optional[str] = None
