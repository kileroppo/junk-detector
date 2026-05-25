"""Tests for the composable scoring pipeline (src.core.pipeline).

Verifies stage execution order, error handling, and context propagation.
All stages are mocked to test pipeline orchestration behavior.
"""

from __future__ import annotations

from src.core.pipeline import PipelineContext, ScoringPipeline


class TestScoringPipeline:
    """Tests for the ScoringPipeline class."""

    async def test_stages_execute_in_order(self):
        """Pipeline stages execute in the order they were added."""
        execution_order = []

        async def stage_a(ctx):
            execution_order.append("a")
            return ctx

        async def stage_b(ctx):
            execution_order.append("b")
            return ctx

        async def stage_c(ctx):
            execution_order.append("c")
            return ctx

        pipeline = ScoringPipeline()
        pipeline.add_stage("a", stage_a)
        pipeline.add_stage("b", stage_b)
        pipeline.add_stage("c", stage_c)

        ctx = PipelineContext(raw_input="test", input_type="text")
        await pipeline.run(ctx)
        assert execution_order == ["a", "b", "c"]

    async def test_critical_stage_failure_halts_pipeline(self):
        """When a critical stage (extract/score) fails, pipeline stops."""
        executed = []

        async def extract_stage(ctx):
            raise ValueError("extraction failed")

        async def score_stage(ctx):
            executed.append("score")
            return ctx

        pipeline = ScoringPipeline()
        pipeline.add_stage("extract", extract_stage)
        pipeline.add_stage("score", score_stage)

        ctx = PipelineContext(raw_input="test", input_type="url")
        result = await pipeline.run(ctx)
        assert "score" not in executed
        assert len(result.errors) == 1
        assert "extract" in result.errors[0]

    async def test_non_critical_stage_failure_continues(self):
        """Non-critical stage failures are logged but pipeline continues."""

        async def enrich_stage(ctx):
            raise RuntimeError("enrichment service unavailable")

        async def score_stage(ctx):
            ctx.stages_executed.append("score_ran")
            return ctx

        pipeline = ScoringPipeline()
        pipeline.add_stage("enrich", enrich_stage)
        pipeline.add_stage("score", score_stage)

        ctx = PipelineContext(raw_input="test", input_type="text")
        result = await pipeline.run(ctx)
        # score stage still ran despite enrich failure
        assert "score" in result.stages_executed
        assert len(result.errors) == 1

    async def test_add_remove_replace_stage(self):
        """add_stage, remove_stage, and replace_stage modify the pipeline."""

        async def dummy(ctx):
            return ctx

        async def replacement(ctx):
            ctx.metadata["replaced"] = True
            return ctx

        pipeline = ScoringPipeline()
        pipeline.add_stage("a", dummy)
        pipeline.add_stage("b", dummy)
        pipeline.add_stage("c", dummy)

        assert pipeline.stage_names == ["a", "b", "c"]

        pipeline.remove_stage("b")
        assert pipeline.stage_names == ["a", "c"]

        pipeline.replace_stage("c", replacement)
        ctx = PipelineContext(raw_input="test", input_type="text")
        result = await pipeline.run(ctx)
        assert result.metadata.get("replaced") is True

    async def test_context_carries_data_between_stages(self):
        """Data set in one stage is available in subsequent stages."""

        async def stage_set(ctx):
            ctx.metadata["key"] = "value_from_stage_1"
            return ctx

        async def stage_read(ctx):
            ctx.metadata["read_result"] = ctx.metadata.get("key", "not_found")
            return ctx

        pipeline = ScoringPipeline()
        pipeline.add_stage("set", stage_set)
        pipeline.add_stage("read", stage_read)

        ctx = PipelineContext(raw_input="test", input_type="text")
        result = await pipeline.run(ctx)
        assert result.metadata["read_result"] == "value_from_stage_1"

    async def test_empty_pipeline_returns_context_unchanged(self):
        """Running an empty pipeline returns the original context."""
        pipeline = ScoringPipeline()
        ctx = PipelineContext(raw_input="hello", input_type="text")
        result = await pipeline.run(ctx)
        assert result.raw_input == "hello"
        assert result.stages_executed == []
        assert result.errors == []
