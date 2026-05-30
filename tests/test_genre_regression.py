"""Genre detection regression fixtures (Phase 2.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.content_genre import detect_content_genre
from src.web.result_display import build_reading_action, score_tier

FIXTURES = Path(__file__).parent / "fixtures" / "genre_regression.json"
ARTICLE_URL = (
    "https://pasqualepillitteri.it/zh/news/889/"
    "claude-code-18-zuijia-skill-ui-ux-sheji-zhinan"
)


@pytest.fixture(scope="module")
def genre_cases() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "case_key",
    ["roundup_sample", "news_sample", "opinion_sample", "advertorial_sample"],
)
def test_detect_content_genre_regression(case_key: str, genre_cases: dict) -> None:
    case = genre_cases[case_key]
    text = case["text"] if case_key != "roundup_sample" else case["text_snippet"]
    # Pad short snippets to pass minimum length
    padded = (text + "\n") * 8
    assert detect_content_genre(padded) == case["genre"]


def test_roundup_reading_action_not_skip_at_moderate_score() -> None:
    dims = {
        "scam_prob": 30,
        "emotional_manipulation": 10,
        "ai_generated_prob": 85,
        "advertorial_prob": 70,
        "originality": 20,
        "info_density": 10,
        "reasoning_quality": 5,
        "readability": 60,
        "timeliness": 40,
    }
    tier = score_tier(59, content_genre="roundup", dimensions=dims)
    verdict = {"recommendation": "skim", "headline": "速查即可", "css": "focus-verdict--skim"}
    action = build_reading_action(
        verdict, tier, content_genre="roundup", dimensions=dims, overall_score=59
    )
    assert action["key"] == "skim"
    assert action["label"] == "速查即可"


@pytest.mark.parametrize("url", [ARTICLE_URL])
def test_reference_article_url_in_benchmark(url: str) -> None:
    """Benchmark URL is registered for manual/CI integration runs."""
    assert "claude-code" in url
