#!/usr/bin/env python3
"""Simulate 10-round tuning loop for roundup article scoring (offline, no LLM)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from src.core.config import load_config
from src.core.content_genre import (
    GENRE_DEFAULT,
    GENRE_ROUNDUP,
    apply_genre_calibration,
    compute_reference_value_score,
    detect_content_genre,
)
from src.core.rules import apply_rules
from src.core.scorer import _calculate_overall, _generate_labels
from src.extractors.web import extract_from_url
from src.models.score import DimensionScores
from src.web.result_display import build_reading_verdict, score_tier

ARTICLE_URL = (
    "https://pasqualepillitteri.it/zh/news/889/"
    "claude-code-18-zuijia-skill-ui-ux-sheji-zhinan"
)

# User-reported LLM dimensions (screenshot baseline)
BASELINE_LLM = DimensionScores(
    originality=20,
    info_density=10,
    reasoning_quality=5,
    readability=60,
    timeliness=40,
    ai_generated_prob=85,
    emotional_manipulation=10,
    advertorial_prob=70,
    scam_prob=30,
)


@dataclass
class RoundReport:
    round_no: int
    change: str
    genre: str
    overall: float
    tier: str
    headline: str
    labels: list[str]
    dims: dict[str, float]


def _dims_dict(d: DimensionScores) -> dict[str, float]:
    return d.model_dump()


def evaluate(
    round_no: int,
    change: str,
    dims: DimensionScores,
    genre: str,
    *,
    weights: dict[str, float] | None = None,
) -> RoundReport:
    cfg = load_config()
    w = weights or cfg.weights
    overall = _calculate_overall(dims, cfg.model_copy(update={"weights": w}))
    tier = score_tier(overall, content_genre=genre, dimensions=_dims_dict(dims))
    rv = build_reading_verdict(
        None,
        tier,
        overall,
        {"top_risks": [], "top_positive": []},
        content_genre=genre,
    )
    labels = _generate_labels(dims, cfg)
    if genre == GENRE_ROUNDUP and "汇编参考" not in labels:
        labels.append("汇编参考")
    return RoundReport(
        round_no=round_no,
        change=change,
        genre=genre,
        overall=overall,
        tier=tier["label"],
        headline=rv["headline"],
        labels=labels,
        dims=_dims_dict(dims),
    )


async def main() -> None:
    content = await extract_from_url(ARTICLE_URL)
    text = content.text
    genre = detect_content_genre(text)
    ref_score = compute_reference_value_score(text)
    rules = apply_rules(text)

    reports: list[RoundReport] = []

    # R1 baseline
    reports.append(
        evaluate(1, "基线（用户截图 LLM 维度）", BASELINE_LLM, GENRE_DEFAULT)
    )

    # R2 genre detect only
    reports.append(
        evaluate(2, "仅识别体裁，未校准", BASELINE_LLM, genre)
    )

    # R3 first calibration
    d3 = apply_genre_calibration(BASELINE_LLM, GENRE_ROUNDUP)
    reports.append(evaluate(3, "体裁校准 v1", d3, genre))

    # R4 reference value blend into info_density
    from src.core.content_genre import blend_roundup_reference_density

    d4 = blend_roundup_reference_density(BASELINE_LLM, ref_score)
    d4 = apply_genre_calibration(d4, GENRE_ROUNDUP)
    reports.append(evaluate(4, f"参考价值融合 ref={ref_score:.0f}", d4, genre))

    # R5 genre weights
    from src.core.content_genre import roundup_scoring_weights

    d5 = blend_roundup_reference_density(BASELINE_LLM, ref_score)
    d5 = apply_genre_calibration(d5, GENRE_ROUNDUP)
    reports.append(
        evaluate(5, "汇编专用权重", d5, genre, weights=roundup_scoring_weights())
    )

    # R6 calibration v2 + label filter
    from src.core.content_genre import apply_genre_calibration_v2, filter_roundup_labels

    d6 = blend_roundup_reference_density(BASELINE_LLM, ref_score)
    d6 = apply_genre_calibration_v2(d6, GENRE_ROUNDUP, text)
    labels6 = filter_roundup_labels(_generate_labels(d6, load_config()))
    r6 = evaluate(6, "校准 v2 + 标签过滤", d6, genre, weights=roundup_scoring_weights())
    r6.labels = labels6
    reports.append(r6)

    # R7 rules-aware advertorial cap
    from src.core.content_genre import cap_roundup_risk_from_rules

    d7 = cap_roundup_risk_from_rules(d6, rules)
    r7 = evaluate(7, "规则层风险封顶", d7, genre, weights=roundup_scoring_weights())
    r7.labels = filter_roundup_labels(_generate_labels(d7, load_config()))
    reports.append(r7)

    # R8 timeliness boost for dated tool roundup
    from src.core.content_genre import boost_roundup_timeliness

    d8 = boost_roundup_timeliness(d7)
    r8 = evaluate(8, "工具文时效性上调", d8, genre, weights=roundup_scoring_weights())
    r8.labels = filter_roundup_labels(_generate_labels(d8, load_config()))
    reports.append(r8)

    # R9 full pipeline helper (single entry)
    from src.core.content_genre import finalize_roundup_dimensions

    d9 = finalize_roundup_dimensions(BASELINE_LLM, text, rules)
    r9 = evaluate(9, "finalize_roundup_dimensions", d9, genre, weights=roundup_scoring_weights())
    r9.labels = filter_roundup_labels(_generate_labels(d9, load_config()))
    reports.append(r9)

    # R10 target band check
    reports.append(
        evaluate(
            10,
            "目标验收（52-68 汇编参考）",
            d9,
            genre,
            weights=roundup_scoring_weights(),
        )
    )
    reports[-1].labels = filter_roundup_labels(_generate_labels(d9, load_config()))

    print(json.dumps([r.__dict__ for r in reports], ensure_ascii=False, indent=2))
    ok = 52 <= reports[-1].overall <= 68 and reports[-1].tier == "汇编参考"
    print(f"\nTARGET_OK={ok} final_score={reports[-1].overall}")


if __name__ == "__main__":
    asyncio.run(main())
