"""Tests for pipeline stages (src.core.pipeline_stages).

Covers extract_stage, enrich_stage, preprocess_stage, score_stage, and postprocess_stage
with mocked dependencies to avoid actual I/O, API calls, and DB writes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.pipeline import PipelineContext
from src.models.score import Content, DimensionScores, ScoreResult, ScoringConfig


# --- Fixtures ---


@pytest.fixture
def text_ctx():
    """PipelineContext for text input."""
    ctx = PipelineContext(raw_input="This is a test article text.", input_type="text")
    ctx.config = ScoringConfig()
    return ctx


@pytest.fixture
def url_ctx():
    """PipelineContext for URL input."""
    ctx = PipelineContext(raw_input="https://example.com/article", input_type="url")
    ctx.config = ScoringConfig()
    return ctx


@pytest.fixture
def file_ctx():
    """PipelineContext for file input."""
    ctx = PipelineContext(raw_input="/path/to/article.txt", input_type="file")
    ctx.config = ScoringConfig()
    return ctx


@pytest.fixture
def sample_content():
    """A minimal Content object for testing."""
    return Content(
        input_type="text",
        text="A" * 200,  # 200 chars, above short threshold
        source_url="https://example.com",
        title="Test Article",
        content_hash="abc123",
    )


@pytest.fixture
def sample_result():
    """A minimal ScoreResult for postprocess testing."""
    return ScoreResult(
        overall_score=65.0,
        dimensions=DimensionScores(
            originality=70,
            info_density=60,
            reasoning_quality=65,
            readability=80,
            timeliness=50,
            ai_generated_prob=20,
            emotional_manipulation=15,
            advertorial_prob=10,
            scam_prob=5,
        ),
        labels=["test-label"],
        summary="Test summary",
        confidence=0.85,
        model_used="test-model",
    )


# --- extract_stage tests ---


class TestExtractStage:
    """Tests for extract_stage."""

    @pytest.mark.asyncio
    @patch("src.extractors.text.extract_from_text")
    async def test_text_input_calls_extract_from_text(self, mock_extract, text_ctx):
        from src.core.pipeline_stages import extract_stage

        fake_content = Content(input_type="text", text="extracted", content_hash="h1")
        mock_extract.return_value = fake_content

        result = await extract_stage(text_ctx)

        mock_extract.assert_called_once_with(text_ctx.raw_input)
        assert result.content == fake_content

    @pytest.mark.asyncio
    @patch("src.extractors.text.extract_from_file")
    async def test_file_input_calls_extract_from_file(self, mock_extract, file_ctx):
        from src.core.pipeline_stages import extract_stage

        fake_content = Content(input_type="file", text="file content", content_hash="h2")
        mock_extract.return_value = fake_content

        result = await extract_stage(file_ctx)

        mock_extract.assert_called_once_with(file_ctx.raw_input)
        assert result.content == fake_content

    @pytest.mark.asyncio
    @patch("src.extractors.playwright_web.smart_extract", new_callable=AsyncMock)
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    async def test_url_input_with_smart_extract(self, mock_url, mock_smart, url_ctx):
        from src.core.pipeline_stages import extract_stage

        fake_content = Content(input_type="url", text="smart content", content_hash="h3")
        mock_smart.return_value = fake_content

        result = await extract_stage(url_ctx)

        mock_smart.assert_called_once_with(url_ctx.raw_input)
        mock_url.assert_not_called()
        assert result.content == fake_content

    @pytest.mark.asyncio
    @patch("src.extractors.web.extract_from_url", new_callable=AsyncMock)
    async def test_url_input_fallback_when_smart_extract_unavailable(self, mock_url, url_ctx):
        from src.core.pipeline_stages import extract_stage

        fake_content = Content(input_type="url", text="url content", content_hash="h4")
        mock_url.return_value = fake_content

        # Simulate smart_extract not being importable
        with patch(
            "src.extractors.playwright_web.smart_extract",
            side_effect=ImportError("no playwright"),
        ):
            # We need to force the ImportError inside extract_stage
            # The import happens inside the function, so we patch at module level
            with patch.dict(
                "sys.modules",
                {"src.extractors.playwright_web": None},
            ):
                result = await extract_stage(url_ctx)

        mock_url.assert_called_once_with(url_ctx.raw_input)
        assert result.content == fake_content


# --- enrich_stage tests ---


class TestEnrichStage:
    """Tests for enrich_stage."""

    @pytest.mark.asyncio
    @patch("src.core.content_fingerprint.find_similar")
    @patch("src.core.hydrators.hydrate_article_stats", new_callable=AsyncMock)
    @patch("src.core.hydrators.hydrate_source_reputation", new_callable=AsyncMock)
    async def test_hydrators_update_metadata(
        self, mock_rep, mock_stats, mock_find, text_ctx, sample_content
    ):
        from src.core.pipeline_stages import enrich_stage

        text_ctx.content = sample_content
        mock_rep.return_value = {"source_reputation": 85, "source_domain": "example.com"}
        mock_stats.return_value = {"char_count": 200, "paragraph_count": 3}
        mock_find.return_value = []

        result = await enrich_stage(text_ctx)

        assert result.metadata["source_reputation"] == 85
        assert result.metadata["source_domain"] == "example.com"
        assert result.metadata["char_count"] == 200
        assert result.metadata["paragraph_count"] == 3

    @pytest.mark.asyncio
    @patch("src.core.content_fingerprint.find_similar")
    @patch("src.core.hydrators.hydrate_article_stats", new_callable=AsyncMock)
    @patch("src.core.hydrators.hydrate_source_reputation", new_callable=AsyncMock)
    async def test_hydrator_failure_adds_error(
        self, mock_rep, mock_stats, mock_find, text_ctx, sample_content
    ):
        from src.core.pipeline_stages import enrich_stage

        text_ctx.content = sample_content
        mock_rep.side_effect = RuntimeError("DB connection failed")
        mock_stats.return_value = {"char_count": 100}
        mock_find.return_value = []

        result = await enrich_stage(text_ctx)

        # The failed hydrator should produce an error entry
        assert any("source_reputation" in e for e in result.errors)
        # The other hydrator should still succeed
        assert result.metadata["char_count"] == 100

    @pytest.mark.asyncio
    @patch("src.core.content_fingerprint.find_similar")
    @patch("src.core.hydrators.hydrate_article_stats", new_callable=AsyncMock)
    @patch("src.core.hydrators.hydrate_source_reputation", new_callable=AsyncMock)
    async def test_find_similar_returns_matches(
        self, mock_rep, mock_stats, mock_find, text_ctx, sample_content
    ):
        from src.core.pipeline_stages import enrich_stage

        text_ctx.content = sample_content
        mock_rep.return_value = {}
        mock_stats.return_value = {}

        # Create a fake FingerprintMatch
        fake_match = MagicMock()
        fake_match.title = "Similar Article"
        fake_match.similarity = 0.92
        fake_match.hamming_distance = 3
        mock_find.return_value = [fake_match]

        result = await enrich_stage(text_ctx)

        assert "fingerprint_matches" in result.metadata
        assert result.metadata["fingerprint_matches"][0]["title"] == "Similar Article"
        assert result.metadata["fingerprint_matches"][0]["similarity"] == 0.92

    @pytest.mark.asyncio
    @patch("src.core.content_fingerprint.find_similar", side_effect=Exception("DB error"))
    @patch("src.core.hydrators.hydrate_article_stats", new_callable=AsyncMock)
    @patch("src.core.hydrators.hydrate_source_reputation", new_callable=AsyncMock)
    async def test_find_similar_failure_is_handled_gracefully(
        self, mock_rep, mock_stats, mock_find, text_ctx, sample_content
    ):
        from src.core.pipeline_stages import enrich_stage

        text_ctx.content = sample_content
        mock_rep.return_value = {}
        mock_stats.return_value = {}

        # Should not raise, fingerprint failure is non-blocking
        result = await enrich_stage(text_ctx)

        assert "fingerprint_matches" not in result.metadata


# --- preprocess_stage tests ---


class TestPreprocessStage:
    """Tests for preprocess_stage."""

    @pytest.mark.asyncio
    async def test_none_content_uses_raw_input(self, text_ctx):
        from src.core.pipeline_stages import preprocess_stage

        text_ctx.content = None

        result = await preprocess_stage(text_ctx)

        assert result.processed_text == text_ctx.raw_input

    @pytest.mark.asyncio
    async def test_short_text_flags_metadata(self, text_ctx):
        from src.core.pipeline_stages import preprocess_stage

        text_ctx.content = Content(
            input_type="text", text="Short text", content_hash="h"
        )

        result = await preprocess_stage(text_ctx)

        assert result.metadata["short_content"] is True
        assert result.processed_text == "Short text"

    @pytest.mark.asyncio
    async def test_normal_text_sets_processed_text(self, text_ctx, sample_content):
        from src.core.pipeline_stages import preprocess_stage

        text_ctx.content = sample_content
        # 200 chars, above 100, below summarize_max_chars (5000)
        text_ctx.config.summarize_enabled = True

        result = await preprocess_stage(text_ctx)

        assert result.processed_text == sample_content.text
        assert "short_content" not in result.metadata

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_long_text_with_summarize_enabled(self, mock_llm, text_ctx):
        from src.core.pipeline_stages import preprocess_stage

        long_text = "A" * 6000  # exceeds default summarize_max_chars (5000)
        text_ctx.content = Content(input_type="text", text=long_text, content_hash="h")
        text_ctx.config.summarize_enabled = True
        text_ctx.config.summarize_max_chars = 5000

        # Mock litellm response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summarized text"
        mock_llm.return_value = mock_response

        result = await preprocess_stage(text_ctx)

        assert result.processed_text == "Summarized text"
        assert result.metadata["was_summarized"] is True
        assert result.metadata["original_length"] == 6000

    @pytest.mark.asyncio
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_summarization_failure_truncates(self, mock_llm, text_ctx):
        from src.core.pipeline_stages import preprocess_stage

        long_text = "B" * 6000
        text_ctx.content = Content(input_type="text", text=long_text, content_hash="h")
        text_ctx.config.summarize_enabled = True
        text_ctx.config.summarize_max_chars = 5000

        mock_llm.side_effect = RuntimeError("API timeout")

        result = await preprocess_stage(text_ctx)

        # Should fall back to truncation
        assert result.processed_text == long_text[:5000]
        assert result.metadata["was_truncated"] is True

    @pytest.mark.asyncio
    async def test_long_text_with_summarize_disabled(self, text_ctx):
        from src.core.pipeline_stages import preprocess_stage

        long_text = "C" * 6000
        text_ctx.content = Content(input_type="text", text=long_text, content_hash="h")
        text_ctx.config.summarize_enabled = False

        result = await preprocess_stage(text_ctx)

        assert result.processed_text == long_text


# --- score_stage tests ---


class TestScoreStage:
    """Tests for score_stage."""

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    async def test_score_stage_calls_scorer(self, mock_score, text_ctx, sample_result):
        from src.core.pipeline_stages import score_stage

        mock_score.return_value = sample_result
        text_ctx.processed_text = "processed text to score"

        result = await score_stage(text_ctx)

        mock_score.assert_called_once_with(
            "processed text to score", config=text_ctx.config, language="zh"
        )
        assert result.result == sample_result

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    async def test_score_stage_uses_content_text_as_fallback(
        self, mock_score, text_ctx, sample_content, sample_result
    ):
        from src.core.pipeline_stages import score_stage

        mock_score.return_value = sample_result
        text_ctx.processed_text = None
        text_ctx.content = sample_content

        result = await score_stage(text_ctx)

        mock_score.assert_called_once_with(
            sample_content.text, config=text_ctx.config, language="zh"
        )
        assert result.result == sample_result

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    async def test_score_stage_uses_raw_input_as_last_resort(
        self, mock_score, text_ctx, sample_result
    ):
        from src.core.pipeline_stages import score_stage

        mock_score.return_value = sample_result
        text_ctx.processed_text = None
        text_ctx.content = None

        result = await score_stage(text_ctx)

        mock_score.assert_called_once_with(
            text_ctx.raw_input, config=text_ctx.config, language="zh"
        )
        assert result.result == sample_result

    @pytest.mark.asyncio
    @patch("src.core.scorer.score", new_callable=AsyncMock)
    async def test_score_stage_respects_language_metadata(
        self, mock_score, text_ctx, sample_result
    ):
        from src.core.pipeline_stages import score_stage

        mock_score.return_value = sample_result
        text_ctx.processed_text = "some text"
        text_ctx.metadata["language"] = "en"

        await score_stage(text_ctx)

        mock_score.assert_called_once_with(
            "some text", config=text_ctx.config, language="en"
        )


# --- postprocess_stage tests ---


class TestPostprocessStage:
    """Tests for postprocess_stage."""

    @pytest.mark.asyncio
    @patch("src.core.pipeline_stages._save_result", new_callable=AsyncMock)
    @patch("src.core.source_reputation.get_source_adjustment", return_value=(0, ""))
    @patch("src.core.content_fingerprint.save_fingerprint")
    @patch("src.core.side_effects.base.SideEffectRunner")
    async def test_originality_penalty_on_high_similarity(
        self, mock_runner, mock_fp, mock_adj, mock_save, text_ctx, sample_content, sample_result
    ):
        from src.core.pipeline_stages import postprocess_stage

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_all = AsyncMock()
        mock_runner.return_value = mock_runner_instance

        text_ctx.content = sample_content
        text_ctx.result = sample_result
        text_ctx.metadata["max_similarity"] = 0.95

        original_originality = sample_result.dimensions.originality

        result = await postprocess_stage(text_ctx)

        # Originality should be reduced
        assert result.result.dimensions.originality < original_originality
        # Label should be added
        assert "疑似搬运" in result.result.labels
        # Penalty recorded in metadata
        assert result.metadata.get("originality_penalty_applied") is not None

    @pytest.mark.asyncio
    @patch("src.core.pipeline_stages._save_result", new_callable=AsyncMock)
    @patch("src.core.source_reputation.get_source_adjustment", return_value=(0, ""))
    @patch("src.core.content_fingerprint.save_fingerprint")
    @patch("src.core.side_effects.base.SideEffectRunner")
    async def test_source_reputation_note_on_low_reputation(
        self, mock_runner, mock_fp, mock_adj, mock_save, text_ctx, sample_content, sample_result
    ):
        from src.core.pipeline_stages import postprocess_stage

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_all = AsyncMock()
        mock_runner.return_value = mock_runner_instance

        text_ctx.content = sample_content
        text_ctx.result = sample_result
        text_ctx.metadata["source_reputation"] = 30
        text_ctx.metadata["source_domain"] = "spam.example.com"

        result = await postprocess_stage(text_ctx)

        assert "spam.example.com" in result.result.summary
        assert "30" in result.result.summary

    @pytest.mark.asyncio
    @patch("src.core.pipeline_stages._save_result", new_callable=AsyncMock)
    @patch("src.core.source_reputation.get_source_adjustment", return_value=(-20, "黑名单来源"))
    @patch("src.core.content_fingerprint.save_fingerprint")
    @patch("src.core.side_effects.base.SideEffectRunner")
    async def test_negative_source_adjustment(
        self, mock_runner, mock_fp, mock_adj, mock_save, text_ctx, sample_content, sample_result
    ):
        from src.core.pipeline_stages import postprocess_stage

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_all = AsyncMock()
        mock_runner.return_value = mock_runner_instance

        text_ctx.content = sample_content
        text_ctx.result = sample_result
        original_score = sample_result.overall_score

        result = await postprocess_stage(text_ctx)

        assert result.result.overall_score == original_score - 20
        assert "黑名单来源" in result.result.labels
        assert result.metadata["source_adjustment"] == -20

    @pytest.mark.asyncio
    @patch("src.core.pipeline_stages._save_result", new_callable=AsyncMock)
    @patch("src.core.source_reputation.get_source_adjustment", return_value=(15, "可信来源"))
    @patch("src.core.content_fingerprint.save_fingerprint")
    @patch("src.core.side_effects.base.SideEffectRunner")
    async def test_positive_source_adjustment(
        self, mock_runner, mock_fp, mock_adj, mock_save, text_ctx, sample_content, sample_result
    ):
        from src.core.pipeline_stages import postprocess_stage

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_all = AsyncMock()
        mock_runner.return_value = mock_runner_instance

        text_ctx.content = sample_content
        text_ctx.result = sample_result
        original_score = sample_result.overall_score

        result = await postprocess_stage(text_ctx)

        assert result.result.overall_score == original_score + 15
        assert "可信来源" in result.result.labels
        assert result.metadata["source_adjustment"] == 15

    @pytest.mark.asyncio
    @patch("src.core.pipeline_stages._save_result", new_callable=AsyncMock)
    @patch("src.core.source_reputation.get_source_adjustment", return_value=(0, ""))
    @patch("src.core.content_fingerprint.save_fingerprint")
    @patch("src.core.side_effects.base.SideEffectRunner")
    async def test_no_result_returns_early(
        self, mock_runner, mock_fp, mock_adj, mock_save, text_ctx
    ):
        from src.core.pipeline_stages import postprocess_stage

        text_ctx.result = None

        result = await postprocess_stage(text_ctx)

        assert result.result is None
        mock_save.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.core.pipeline_stages._save_result", new_callable=AsyncMock)
    @patch("src.core.source_reputation.get_source_adjustment", return_value=(0, ""))
    @patch("src.core.content_fingerprint.save_fingerprint")
    @patch("src.core.side_effects.base.SideEffectRunner")
    async def test_save_failure_adds_error(
        self, mock_runner, mock_fp, mock_adj, mock_save, text_ctx, sample_content, sample_result
    ):
        from src.core.pipeline_stages import postprocess_stage

        mock_runner_instance = MagicMock()
        mock_runner_instance.run_all = AsyncMock()
        mock_runner.return_value = mock_runner_instance

        text_ctx.content = sample_content
        text_ctx.result = sample_result
        mock_save.side_effect = RuntimeError("DB write failed")

        result = await postprocess_stage(text_ctx)

        assert any("postprocess/save" in e for e in result.errors)


# --- _get_db_path tests ---


class TestGetDbPath:
    """Tests for the _get_db_path helper."""

    def test_default_path(self, text_ctx):
        from src.core.pipeline_stages import _get_db_path

        assert _get_db_path(text_ctx) == "junk_detector.db"

    def test_custom_path_from_metadata(self, text_ctx):
        from src.core.pipeline_stages import _get_db_path

        text_ctx.metadata["db_path"] = "/custom/path.db"
        assert _get_db_path(text_ctx) == "/custom/path.db"
