"""Composable scoring pipeline inspired by x-algorithm's Candidate Pipeline.

Stages run in order: extract → enrich → preprocess → score → postprocess
Each stage is a callable that transforms a PipelineContext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from src.models.score import Content, ScoreResult, ScoringConfig


@dataclass
class PipelineContext:
    """Context object passed through all pipeline stages."""

    # Input
    raw_input: str  # original URL or text
    input_type: str  # "url", "text", "file"

    # After extraction
    content: Content | None = None

    # Enrichment metadata (from hydrators)
    metadata: dict[str, Any] = field(default_factory=dict)
    # e.g. {"author_history": {...}, "source_reputation": 0.8, "similar_articles": [...]}

    # After preprocessing (e.g. summarization)
    processed_text: str | None = None  # text that actually gets scored

    # After scoring
    result: ScoreResult | None = None

    # Configuration
    config: ScoringConfig = field(default_factory=ScoringConfig)

    # Pipeline execution metadata
    stages_executed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Stage type: async function that takes context, returns context
Stage = Callable[[PipelineContext], Awaitable[PipelineContext]]


class ScoringPipeline:
    """Orchestrates the scoring pipeline with registered stages."""

    def __init__(self):
        self._stages: list[tuple[str, Stage]] = []

    def add_stage(self, name: str, stage: Stage) -> "ScoringPipeline":
        """Register a pipeline stage. Returns self for fluent chaining."""
        self._stages.append((name, stage))
        return self

    def remove_stage(self, name: str) -> "ScoringPipeline":
        """Remove a stage by name. Returns self for fluent chaining."""
        self._stages = [(n, s) for n, s in self._stages if n != name]
        return self

    def replace_stage(self, name: str, stage: Stage) -> "ScoringPipeline":
        """Replace a stage by name. If not found, appends it."""
        replaced = False
        new_stages = []
        for n, s in self._stages:
            if n == name:
                new_stages.append((name, stage))
                replaced = True
            else:
                new_stages.append((n, s))
        if not replaced:
            new_stages.append((name, stage))
        self._stages = new_stages
        return self

    @property
    def stage_names(self) -> list[str]:
        """Return the list of registered stage names in order."""
        return [name for name, _ in self._stages]

    async def run(self, context: PipelineContext) -> PipelineContext:
        """Execute all stages in order.

        Critical stages ('extract', 'score') will halt the pipeline on failure.
        Non-critical stages log errors and continue.
        """
        for name, stage in self._stages:
            try:
                context = await stage(context)
                context.stages_executed.append(name)
            except Exception as e:
                context.errors.append(f"{name}: {e}")
                # Continue pipeline unless it's a critical stage
                if name in ("extract", "score"):
                    break
        return context


def build_default_pipeline() -> ScoringPipeline:
    """Build the default scoring pipeline with all stages.

    Stages:
        1. extract   — turn raw_input into Content
        2. enrich    — hydrate metadata (source reputation, article stats)
        3. preprocess — summarize long articles, prepare text for scoring
        4. score     — run rules + LLM judge
        5. postprocess — apply metadata adjustments, persist results
    """
    from src.core.pipeline_stages import (
        enrich_stage,
        extract_stage,
        postprocess_stage,
        preprocess_stage,
        score_stage,
    )

    pipeline = ScoringPipeline()
    pipeline.add_stage("extract", extract_stage)
    pipeline.add_stage("enrich", enrich_stage)
    pipeline.add_stage("preprocess", preprocess_stage)
    pipeline.add_stage("score", score_stage)
    pipeline.add_stage("postprocess", postprocess_stage)
    return pipeline
