"""Lightweight content genre detection for scoring calibration."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.rules import RuleResult
    from src.models.score import DimensionScores

GENRE_DEFAULT = "default"
GENRE_ROUNDUP = "roundup"

_ROUNDUP_NUMBERED = re.compile(r"(?m)^\s*\d+[\.\)、]")
_ROUNDUP_GITHUB = re.compile(r"github\.com", re.I)
_INSTALL_MARKERS = (
    "npx skills add",
    "plugin marketplace",
    "claude plugin add",
    "/plugin marketplace",
    "skills add",
    "marketplace add",
    "plugin add",
)

# Tunable profile (10-round offline tuning on reference roundup articles)
ROUNDUP_CALIBRATION = {
    "info_density_floor": 45.0,
    "reasoning_floor": 32.0,
    "readability_floor": 55.0,
    "timeliness_floor": 48.0,
    "ai_cap": 68.0,
    "advertorial_cap": 58.0,
    "scam_cap": 30.0,
    "reference_blend": 0.55,  # weight of heuristic reference score vs LLM info_density
}

ROUNDUP_WEIGHTS: dict[str, float] = {
    "originality": 0.85,
    "info_density": 1.15,
    "reasoning_quality": 0.35,
    "readability": 0.75,
    "timeliness": 0.65,
    "ai_generated_prob": -0.55,
    "emotional_manipulation": -1.0,
    "advertorial_prob": -0.75,
    "scam_prob": -1.15,
}

_BANNED_ROUNDUP_SUMMARY_FRAGMENTS = (
    "seo垃圾",
    "seo 垃圾",
    "内容空洞",
    "标题夸大",
    "高风险",
    "骗局",
    "垃圾内容",
)


def detect_content_genre(text: str) -> str:
    """Detect reference roundup / tool list articles (heuristic, no LLM)."""
    if not text or len(text.strip()) < 200:
        return GENRE_DEFAULT

    signals = 0
    numbered = len(_ROUNDUP_NUMBERED.findall(text))
    if numbered >= 4:
        signals += 1
    github_hits = len(_ROUNDUP_GITHUB.findall(text))
    if github_hits >= 2:
        signals += 1
    if sum(1 for m in _INSTALL_MARKERS if m in text.lower()) >= 1:
        signals += 1
    if "对比表" in text or re.search(r"\|\s*Skill\s*\|", text, re.I):
        signals += 1
    if re.search(r"(完整指南|选型|哪款|清单|盘点|合集|最佳\s*\d+)", text):
        signals += 1

    return GENRE_ROUNDUP if signals >= 2 else GENRE_DEFAULT


def compute_reference_value_score(text: str) -> float:
    """Heuristic 0-100: actionable reference density (repos, commands, structure)."""
    if not text:
        return 0.0
    score = 28.0
    github_hits = len(_ROUNDUP_GITHUB.findall(text))
    score += min(28, github_hits * 2.5)
    numbered = len(_ROUNDUP_NUMBERED.findall(text))
    score += min(18, numbered * 1.8)
    installs = sum(1 for m in _INSTALL_MARKERS if m in text.lower())
    score += min(14, installs * 5)
    if "对比表" in text or re.search(r"\|\s*Skill\s*\|", text, re.I):
        score += 12
    if re.search(r"(仓库|安装|stars|star\)|插件)", text, re.I):
        score += 6
    return round(max(0.0, min(100.0, score)), 1)


def genre_system_prompt_addon(genre: str, language: str = "zh") -> str:
    """Extra instructions appended to the scoring system prompt."""
    if genre != GENRE_ROUNDUP:
        return ""
    if language == "en":
        return (
            "\n\n## Content genre: reference roundup / tool list\n"
            "This is a curated list (repos, install commands, comparison table), not an essay.\n"
            "- info_density: score actionable reference value (links, commands, tables), not depth of argument.\n"
            "- reasoning_quality: may be moderate (30-50); do not score near zero only because there is no thesis.\n"
            "- advertorial_prob: distinguish catalog-style outbound links from disguised personal endorsements.\n"
            "- ai_generated_prob: template SEO tone is not the same as scam or worthless spam.\n"
            "- scam_prob: only high if there are get-rich-quick, private chat, or investment harvest cues.\n"
            "- summary: state who should use it as a quick reference and any marketing caveats; "
            "avoid labels like 'SEO garbage' unless scam_prob would be >= 60.\n"
        )
    return (
        "\n\n## 内容体裁：工具/资源清单（汇编参考）\n"
        "本文为清单型汇编（仓库链接、安装命令、对比表），不是论证型长文。\n"
        "- info_density：按可执行参考价值评分（命令、仓库、对比表），勿因缺少深度论证给极低分。\n"
        "- reasoning_quality：可给中等分（30-50），勿仅因无中心论点给个位数。\n"
        "- advertorial_prob：区分目录式外链与伪装个人体验的带货软文。\n"
        "- ai_generated_prob：模板化 SEO 文风不等于诈骗或毫无阅读价值。\n"
        "- scam_prob：仅在有躺赚、私聊收割、投资诱导等话术时给高分。\n"
        "- summary：说明适合当作选型速查还是不宜深读，并提示内容营销/低原创；"
        "除非 scam_prob≥60，避免使用「SEO垃圾」「内容空洞」等笼统贬损表述。\n"
    )


def roundup_summarize_prompt(language: str = "zh") -> str:
    """Prompt for summarizing long roundup articles before scoring."""
    if language == "en":
        return (
            "Summarize this reference roundup in Chinese (<=1500 chars). Preserve structure:\n"
            "1) One-line purpose 2) Comparison table or selection criteria if any "
            "3) For each item: name, use case, install command, repo link (keep commands verbatim)\n"
            "Skip site chrome, newsletter signup, and related-article lists.\n\n"
        )
    return (
        "请用中文摘要这篇工具/资源清单（1500字以内），保留结构：\n"
        "1）一文目的 2）对比表或选型建议（若有） "
        "3）每条：名称、适用场景、安装命令、仓库链接（安装命令原文保留）\n"
        "跳过站点导航、订阅框、相关文章推荐。\n\n"
    )


def apply_genre_calibration(dimensions: "DimensionScores", genre: str) -> "DimensionScores":
    """Post-LLM floor/cap adjustments for roundup content (legacy entry)."""
    return apply_genre_calibration_v2(dimensions, genre, "")


def apply_genre_calibration_v2(
    dimensions: "DimensionScores", genre: str, text: str
) -> "DimensionScores":
    """Post-LLM floor/cap adjustments for roundup content."""
    from src.models.score import DimensionScores

    if genre != GENRE_ROUNDUP:
        return dimensions

    cfg = ROUNDUP_CALIBRATION
    ref = compute_reference_value_score(text) if text else 0.0
    info = max(
        dimensions.info_density,
        cfg["info_density_floor"],
        ref * cfg["reference_blend"] + dimensions.info_density * (1 - cfg["reference_blend"]),
    )

    return DimensionScores(
        originality=dimensions.originality,
        info_density=round(min(100.0, info), 1),
        reasoning_quality=max(dimensions.reasoning_quality, cfg["reasoning_floor"]),
        readability=max(dimensions.readability, cfg["readability_floor"]),
        timeliness=max(dimensions.timeliness, cfg["timeliness_floor"]),
        ai_generated_prob=min(dimensions.ai_generated_prob, cfg["ai_cap"]),
        emotional_manipulation=dimensions.emotional_manipulation,
        advertorial_prob=min(dimensions.advertorial_prob, cfg["advertorial_cap"]),
        scam_prob=min(dimensions.scam_prob, cfg["scam_cap"]),
    )


def blend_roundup_reference_density(
    dimensions: "DimensionScores", reference_score: float
) -> "DimensionScores":
    from src.models.score import DimensionScores

    blend = ROUNDUP_CALIBRATION["reference_blend"]
    merged = reference_score * blend + dimensions.info_density * (1 - blend)
    return dimensions.model_copy(update={"info_density": round(min(100.0, merged), 1)})


def roundup_scoring_weights() -> dict[str, float]:
    return dict(ROUNDUP_WEIGHTS)


def cap_roundup_risk_from_rules(dimensions: "DimensionScores", rule_result: "RuleResult") -> "DimensionScores":
    """Do not let weak promo keyword hits dominate roundup risk."""
    from src.models.score import DimensionScores

    overrides = rule_result.dimension_overrides
    updates: dict[str, float] = {}
    if overrides.get("scam_prob", 0) >= 50 and dimensions.scam_prob < 40:
        updates["scam_prob"] = dimensions.scam_prob
    if overrides.get("advertorial_prob", 0) >= 55:
        updates["advertorial_prob"] = min(dimensions.advertorial_prob, 55.0)
    if not updates:
        return dimensions
    return dimensions.model_copy(update=updates)


def boost_roundup_timeliness(dimensions: "DimensionScores") -> "DimensionScores":
    """Tool roundups on current products are often still useful within the year."""
    if dimensions.timeliness >= 50:
        return dimensions
    return dimensions.model_copy(update={"timeliness": min(65.0, dimensions.timeliness + 12)})


def filter_roundup_labels(labels: list[str]) -> list[str]:
    """Suppress misleading junk labels on reference roundups."""
    out: list[str] = []
    for label in labels:
        if label in ("可能AI生成", "疑似软文"):
            continue
        out.append(label)
    if "汇编参考" not in out:
        out.append("汇编参考")
    return out


def sanitize_roundup_summary(summary: str, dimensions: "DimensionScores") -> str:
    """Replace harsh generic junk wording with reference-oriented copy."""
    lower = (summary or "").lower()
    if not any(frag in lower for frag in _BANNED_ROUNDUP_SUMMARY_FRAGMENTS):
        if dimensions.info_density >= 45:
            return summary
    ad = int(dimensions.advertorial_prob)
    ai = int(dimensions.ai_generated_prob)
    return (
        f"工具清单汇编，可作 Skill 选型速查（原创偏低，AI 痕迹 {ai}%，推广倾向 {ad}%）；"
        "重点看对比表与安装命令，勿当深度论证文阅读。"
    )


def finalize_roundup_dimensions(
    dimensions: "DimensionScores",
    text: str,
    rule_result: "RuleResult | None" = None,
) -> "DimensionScores":
    """Single entry: full roundup post-processing pipeline."""
    ref = compute_reference_value_score(text)
    dims = blend_roundup_reference_density(dimensions, ref)
    dims = apply_genre_calibration_v2(dims, GENRE_ROUNDUP, text)
    if rule_result is not None:
        dims = cap_roundup_risk_from_rules(dims, rule_result)
    dims = boost_roundup_timeliness(dims)
    return dims


def calculate_roundup_overall(dimensions: "DimensionScores", base_config) -> float:
    """Overall score using roundup-specific weights."""
    from src.core.scorer import _calculate_overall

    cfg = base_config.model_copy(update={"weights": roundup_scoring_weights()})
    return _calculate_overall(dimensions, cfg)


def roundup_reading_headline() -> str:
    return "速查目录即可"


def roundup_reading_detail() -> str:
    return "汇编参考文：重点看对比表、仓库链接与安装命令；不必当深度论证文逐段细读。"


def roundup_score_tier_label() -> str:
    return "汇编参考"
