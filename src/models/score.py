"""Core data models for junk-detector scoring system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class InputType(str, Enum):
    URL = "url"
    TEXT = "text"
    FILE = "file"


class Content(BaseModel):
    """Represents extracted content ready for scoring."""

    input_type: InputType
    text: str = Field(..., min_length=1)
    source_url: Optional[str] = None
    title: Optional[str] = None
    content_hash: str = Field(default="", description="SHA256 hash of text content")

    def compute_hash(self) -> str:
        import hashlib

        self.content_hash = hashlib.sha256(self.text.encode()).hexdigest()
        return self.content_hash


class DimensionScores(BaseModel):
    """9-dimension scoring breakdown."""

    # Positive dimensions (higher = better)
    originality: float = Field(..., ge=0, le=100, description="原创性 vs 洗稿/搬运")
    info_density: float = Field(..., ge=0, le=100, description="信息密度/干货比例")
    reasoning_quality: float = Field(..., ge=0, le=100, description="论证质量")
    readability: float = Field(..., ge=0, le=100, description="可读性/结构清晰度")
    timeliness: float = Field(..., ge=0, le=100, description="时效性")

    # Negative dimensions (higher = worse/more risky)
    ai_generated_prob: float = Field(..., ge=0, le=100, description="AI生成概率")
    emotional_manipulation: float = Field(..., ge=0, le=100, description="情绪操纵度")
    advertorial_prob: float = Field(..., ge=0, le=100, description="商业软文概率")
    scam_prob: float = Field(..., ge=0, le=100, description="骗子/韭菜收割概率")


class ScoreResult(BaseModel):
    """Complete scoring result for a piece of content."""

    overall_score: float = Field(..., ge=0, le=100, description="综合评分 0-100")
    dimensions: DimensionScores
    labels: list[str] = Field(default_factory=list, description="标签列表")
    summary: str = Field(..., description="一句话评价")
    confidence: float = Field(default=1.0, ge=0, le=1, description="评分置信度")
    model_used: str = Field(default="", description="使用的模型")
    cost: float = Field(default=0.0, ge=0, description="本次调用成本")
    scored_at: datetime = Field(default_factory=datetime.now)
    rule_hits: list[str] = Field(default_factory=list, description="命中的规则列表")
    dimension_sources: dict[str, str] = Field(
        default_factory=dict, description="每个维度的来源: 'rule' or 'llm'"
    )
    status: str = Field(default="", description="Content quality status: junk/suspicious/normal/quality")
    explanation: str = Field(default="", description="自然语言解释")
    scored_by: str = Field(default="rules", description="Scoring method: 'rules' or model name")
    duration_ms: int = Field(default=0, description="Scoring duration in milliseconds")
    cost_usd: float = Field(default=0.0, description="Estimated LLM API cost in USD")

    @model_validator(mode='after')
    def _compute_status(self) -> 'ScoreResult':
        if self.overall_score < 40:
            self.status = "junk"
        elif self.overall_score <= 60:
            self.status = "suspicious"
        elif self.overall_score <= 80:
            self.status = "normal"
        else:
            self.status = "quality"
        return self


class FastScoreResult(BaseModel):
    """Lightweight scoring result for fast screening (4 dimensions only)."""

    quick_verdict: float = Field(..., ge=0, le=100, description="综合质量评分 0-100")
    scam_prob: float = Field(..., ge=0, le=100, description="骗局/收割概率")
    advertorial_prob: float = Field(..., ge=0, le=100, description="软文/广告概率")
    emotional_manipulation: float = Field(..., ge=0, le=100, description="情绪操纵度")
    originality: float = Field(..., ge=0, le=100, description="原创性")
    summary: str = Field(..., description="一句话评价")
    confidence: float = Field(default=0.8, ge=0, le=1, description="评分置信度")
    model_used: str = Field(default="", description="使用的模型")
    cost: float = Field(default=0.0, ge=0, description="本次调用成本")


class ScoringConfig(BaseModel):
    """Configuration for the scoring system."""

    # Dimension weights for overall score calculation
    weights: dict[str, float] = Field(
        default_factory=lambda: {
            # Positive dimensions (positive weight)
            "originality": 1.0,
            "info_density": 1.0,
            "reasoning_quality": 1.0,
            "readability": 0.8,
            "timeliness": 0.6,
            # Negative dimensions (negative weight)
            "ai_generated_prob": -0.8,
            "emotional_manipulation": -1.0,
            "advertorial_prob": -1.0,
            "scam_prob": -1.2,
        }
    )

    # Model configuration
    primary_model: str = Field(default="deepseek/deepseek-chat", description="主要评分模型")
    fallback_model: str = Field(default="deepseek/deepseek-chat", description="复评模型")
    confidence_threshold: float = Field(default=0.7, ge=0, le=1, description="低于此阈值触发复评")
    api_base: Optional[str] = Field(default=None, description="API base URL (e.g. for Ollama)")

    # Label thresholds
    label_thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "可能AI生成": 70.0,  # ai_generated_prob > 70
            "情绪操纵": 65.0,  # emotional_manipulation > 65
            "疑似软文": 70.0,  # advertorial_prob > 70
            "疑似骗局": 60.0,  # scam_prob > 60
            "高质量原创": 80.0,  # originality > 80
            "信息密度高": 80.0,  # info_density > 80
        }
    )

    # Embedding configuration
    embedding_model: str = Field(
        default="ollama/nomic-embed-text", description="Embedding model for similarity detection"
    )
    embedding_api_base: Optional[str] = Field(
        default=None, description="API base for embedding model"
    )

    # Summarization configuration
    summarize_enabled: bool = Field(
        default=True, description="Whether to summarize long articles before scoring"
    )
    summarize_max_chars: int = Field(
        default=5000, description="Articles longer than this get summarized first"
    )
    summarize_model: Optional[str] = Field(
        default=None, description="Model for summarization (None = use primary_model)"
    )
