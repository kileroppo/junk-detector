"""Tests for retry logic and fallback extraction (FEAT-003)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from src.cli.main import app
from src.models.score import Content, FastScoreResult, InputType, ScoringConfig

runner = CliRunner()


# ---------------------------------------------------------------------------
# Test: LLM timeout in score_fast triggers retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_fast_retries_on_timeout():
    """score_fast should retry once on timeout and succeed on second attempt."""
    from src.core.fast_scorer import score_fast

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"quick_verdict": 75, "scam_prob": 10, "advertorial_prob": 20, "emotional_manipulation": 15, "originality": 80, "summary": "OK", "confidence": 0.9}'
            )
        )
    ]
    mock_response._hidden_params = {}

    # First call raises timeout, second succeeds
    with patch("src.core.fast_scorer.litellm.acompletion") as mock_llm:
        mock_llm.side_effect = [
            httpx.TimeoutException("Connection timed out"),
            mock_response,
        ]

        with patch("src.core.fast_scorer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            config = ScoringConfig()
            result = await score_fast("test content", config=config, max_retries=1)

            assert result.quick_verdict == 75
            assert result.originality == 80
            assert mock_llm.call_count == 2
            mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_score_fast_retry_exhausted_returns_default():
    """score_fast should return default result when retries are exhausted."""
    from src.core.fast_scorer import score_fast

    with patch("src.core.fast_scorer.litellm.acompletion") as mock_llm:
        mock_llm.side_effect = httpx.TimeoutException("Connection timed out")

        with patch("src.core.fast_scorer.asyncio.sleep", new_callable=AsyncMock):
            config = ScoringConfig()
            result = await score_fast("test content", config=config, max_retries=1)

            # Should return default low-confidence result
            assert result.confidence == 0.1
            assert result.quick_verdict == 50.0
            assert (
                result.summary
                == "LLM\u54cd\u5e94\u89e3\u6790\u5931\u8d25\uff0c\u8fd4\u56de\u9ed8\u8ba4\u8bc4\u5206"
            )


# ---------------------------------------------------------------------------
# Test: Web extraction fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_from_url_simple_success():
    """extract_from_url_simple should return content with simple text extraction."""
    from src.extractors.web import extract_from_url_simple

    html = "<html><head><title>Test Page</title></head><body><p>Hello world</p><nav>menu</nav></body></html>"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html

    with patch("src.extractors.web.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await extract_from_url_simple("https://example.com")

        assert "Hello world" in result.text
        # Simple extraction does NOT strip noise tags, so nav content is included
        assert "menu" in result.text
        assert result.title == "Test Page"
        assert result.input_type == InputType.URL


def test_extract_content_fallback_on_primary_failure():
    """_extract_content should fall back to simple extraction when primary fails."""
    from src.cli.main import _extract_content

    fallback_content = Content(
        input_type=InputType.URL,
        text="Fallback content here",
        source_url="https://example.com",
        title="Fallback",
    )

    with patch(
        "src.extractors.web.extract_from_url",
        new_callable=AsyncMock,
        side_effect=ValueError("Primary failed"),
    ):
        with patch(
            "src.extractors.web.extract_from_url_simple",
            new_callable=AsyncMock,
            return_value=fallback_content,
        ):
            result = _extract_content(text=None, url="https://example.com", file=None)
            assert result.text == "Fallback content here"


def test_extract_content_both_methods_fail():
    """_extract_content should raise original error when both extraction methods fail."""
    from src.cli.main import _extract_content

    with patch(
        "src.extractors.web.extract_from_url",
        new_callable=AsyncMock,
        side_effect=ValueError("Primary extraction failed"),
    ):
        with patch(
            "src.extractors.web.extract_from_url_simple",
            new_callable=AsyncMock,
            side_effect=ValueError("Simple also failed"),
        ):
            with pytest.raises(ValueError, match="Primary extraction failed"):
                _extract_content(text=None, url="https://example.com", file=None)


# ---------------------------------------------------------------------------
# Test: --retry flag on CLI commands
# ---------------------------------------------------------------------------


def test_score_command_accepts_retry_flag():
    """The score command should accept --retry flag."""
    with patch("src.cli.main._extract_content") as mock_extract:
        mock_extract.return_value = Content(
            input_type=InputType.TEXT,
            text="Test content for scoring",
            title="Test",
        )
        with patch("src.core.config.load_config") as mock_config:
            mock_config.return_value = ScoringConfig()
            with patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock) as mock_fast:
                mock_fast.return_value = FastScoreResult(
                    quick_verdict=75.0,
                    scam_prob=10.0,
                    advertorial_prob=20.0,
                    emotional_manipulation=15.0,
                    originality=80.0,
                    summary="OK",
                    confidence=0.9,
                    model_used="test-model",
                )
                result = runner.invoke(app, ["score", "--text", "hello", "--fast", "--retry", "3"])
                # Should not error due to unknown flag
                assert result.exit_code == 0 or "retry" not in result.output.lower()


def test_quick_command_accepts_retry_flag():
    """The quick command should accept --retry flag."""
    with patch("src.cli.main._extract_content") as mock_extract:
        mock_extract.return_value = Content(
            input_type=InputType.TEXT,
            text="Test content for scoring",
            title="Test",
        )
        with patch("src.core.config.load_config") as mock_config:
            mock_config.return_value = ScoringConfig()
            with patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock) as mock_fast:
                mock_fast.return_value = FastScoreResult(
                    quick_verdict=75.0,
                    scam_prob=10.0,
                    advertorial_prob=20.0,
                    emotional_manipulation=15.0,
                    originality=80.0,
                    summary="OK",
                    confidence=0.9,
                    model_used="test-model",
                )
                result = runner.invoke(app, ["quick", "--text", "hello", "--retry", "2"])
                assert result.exit_code == 0 or "retry" not in result.output.lower()


def test_batch_command_accepts_retry_flag(tmp_path):
    """The batch command should accept --retry flag."""
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://example.com\n")

    with patch("src.extractors.web.extract_from_url", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = Content(
            input_type=InputType.URL,
            text="Test content",
            source_url="https://example.com",
            title="Test",
        )
        with patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock) as mock_fast:
            mock_fast.return_value = FastScoreResult(
                quick_verdict=75.0,
                scam_prob=10.0,
                advertorial_prob=20.0,
                emotional_manipulation=15.0,
                originality=80.0,
                summary="OK",
                confidence=0.9,
                model_used="test-model",
            )
            result = runner.invoke(app, ["batch", "--urls-file", str(urls_file), "--retry", "3"])
            # Should not fail with "no such option" error
            assert "No such option" not in result.output


# ---------------------------------------------------------------------------
# Test: judge() retries on timeout error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_retries_on_timeout():
    """judge() should retry on timeout errors instead of breaking immediately."""
    from src.core.llm_judge import judge

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"originality": 70, "info_density": 65, "reasoning_quality": 60, "readability": 75, "timeliness": 50, "ai_generated_prob": 30, "emotional_manipulation": 20, "advertorial_prob": 15, "scam_prob": 10, "labels": ["good"], "summary": "Well written", "confidence": 0.85}'
            )
        )
    ]
    mock_response._hidden_params = {}

    # First call raises timeout, second succeeds
    with patch("src.core.llm_judge.litellm.acompletion") as mock_llm:
        mock_llm.side_effect = [
            httpx.TimeoutException("Request timed out"),
            mock_response,
        ]

        with patch("src.core.llm_judge.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            config = ScoringConfig()
            result = await judge("test content", config=config)

            assert result.overall_score > 0
            assert result.dimensions.originality == 70
            assert mock_llm.call_count == 2
            mock_sleep.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_judge_timeout_exhausted_returns_default():
    """judge() should return default result when all timeout retries are exhausted."""
    from src.core.llm_judge import judge

    with patch("src.core.llm_judge.litellm.acompletion") as mock_llm:
        mock_llm.side_effect = httpx.TimeoutException("Request timed out")

        with patch("src.core.llm_judge.asyncio.sleep", new_callable=AsyncMock):
            config = ScoringConfig()
            result = await judge("test content", config=config)

            # Should return default low-confidence result
            assert result.confidence == 0.1
            assert result.overall_score == 50.0


@pytest.mark.asyncio
async def test_judge_non_timeout_exception_breaks_immediately():
    """judge() should still break immediately on non-timeout exceptions."""
    from src.core.llm_judge import judge

    with patch("src.core.llm_judge.litellm.acompletion") as mock_llm:
        mock_llm.side_effect = RuntimeError("Some other API error")

        config = ScoringConfig()
        result = await judge("test content", config=config)

        # Should return default after breaking immediately (only 1 call)
        assert result.confidence == 0.1
        assert mock_llm.call_count == 1


# ---------------------------------------------------------------------------
# Test: score_fast with max_retries=2 retries twice on timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_fast_max_retries_2_retries_twice():
    """score_fast with max_retries=2 should actually retry twice on timeout."""
    from src.core.fast_scorer import score_fast

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"quick_verdict": 80, "scam_prob": 5, "advertorial_prob": 10, "emotional_manipulation": 10, "originality": 85, "summary": "Great", "confidence": 0.95}'
            )
        )
    ]
    mock_response._hidden_params = {}

    # First two calls raise timeout, third succeeds
    with patch("src.core.fast_scorer.litellm.acompletion") as mock_llm:
        mock_llm.side_effect = [
            httpx.TimeoutException("Timeout 1"),
            httpx.TimeoutException("Timeout 2"),
            mock_response,
        ]

        with patch("src.core.fast_scorer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            config = ScoringConfig()
            result = await score_fast("test content", config=config, max_retries=2)

            assert result.quick_verdict == 80
            assert result.originality == 85
            assert mock_llm.call_count == 3
            assert mock_sleep.call_count == 2


# ---------------------------------------------------------------------------
# Test: batch command passes retry flag through to score_fast
# ---------------------------------------------------------------------------


def test_batch_passes_retry_to_score_fast(tmp_path):
    """The batch command should pass the retry flag through to score_fast."""
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text("https://example.com\n")

    with patch("src.extractors.web.extract_from_url", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = Content(
            input_type=InputType.URL,
            text="Test content",
            source_url="https://example.com",
            title="Test",
        )
        with patch("src.core.fast_scorer.score_fast", new_callable=AsyncMock) as mock_fast:
            mock_fast.return_value = FastScoreResult(
                quick_verdict=75.0,
                scam_prob=10.0,
                advertorial_prob=20.0,
                emotional_manipulation=15.0,
                originality=80.0,
                summary="OK",
                confidence=0.9,
                model_used="test-model",
            )
            result = runner.invoke(app, ["batch", "--urls-file", str(urls_file), "--retry", "3"])
            assert result.exit_code == 0, f"Output: {result.output}"
            # Verify score_fast was called with max_retries=3
            mock_fast.assert_called_once()
            assert mock_fast.call_args.kwargs["max_retries"] == 3
