"""Preset scoring modes (consumer / audit / scam guard)."""

from __future__ import annotations

from src.models.score import ScoringConfig

MODE_CONSUMER = "consumer"
MODE_AUDIT = "audit"
MODE_SCAM_GUARD = "scam_guard"

MODE_LABELS: dict[str, str] = {
    MODE_CONSUMER: "日常阅读",
    MODE_AUDIT: "内容审核",
    MODE_SCAM_GUARD: "防骗优先",
}

_WEIGHT_PRESETS: dict[str, dict[str, float]] = {
    MODE_CONSUMER: {},
    MODE_AUDIT: {
        "reasoning_quality": 1.25,
        "originality": 1.15,
        "advertorial_prob": -1.25,
        "ai_generated_prob": -0.95,
    },
    MODE_SCAM_GUARD: {
        "scam_prob": -1.5,
        "emotional_manipulation": -1.2,
        "info_density": 0.85,
        "reasoning_quality": 0.85,
    },
}


def apply_scoring_mode(config: ScoringConfig, mode: str | None) -> ScoringConfig:
    """Merge mode weight overrides into a scoring config copy."""
    if not mode or mode not in _WEIGHT_PRESETS:
        return config
    overrides = _WEIGHT_PRESETS[mode]
    if not overrides:
        return config
    merged = dict(config.weights)
    merged.update(overrides)
    return config.model_copy(update={"weights": merged})
