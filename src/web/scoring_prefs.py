"""Scoring weight helpers for the Web UI settings page."""
from __future__ import annotations

WEB_USER_ID = 0

_WEIGHT_LABELS: dict[str, str] = {
    "originality": "原创性",
    "info_density": "信息密度",
    "reasoning_quality": "论证质量",
    "readability": "可读性",
    "timeliness": "时效性",
    "ai_generated_prob": "AI 生成概率",
    "emotional_manipulation": "情绪操纵",
    "advertorial_prob": "软文概率",
    "scam_prob": "骗局概率",
}

_NEGATIVE_KEYS = frozenset(
    {
        "ai_generated_prob",
        "emotional_manipulation",
        "advertorial_prob",
        "scam_prob",
    }
)


def get_scoring_weight_dims(db_path: str = "junk_detector.db") -> list[dict]:
    """Build slider metadata from merged system + user weights."""
    from src.preferences.service import PreferencesService

    config = PreferencesService.build_scoring_config(WEB_USER_ID, db_path=db_path)
    dims: list[dict] = []
    for key, weight in config.weights.items():
        label = _WEIGHT_LABELS.get(key)
        if label is None:
            continue
        negative = key in _NEGATIVE_KEYS
        dims.append(
            {
                "key": key,
                "label": label,
                "negative": negative,
                "weight": weight,
                "slider_value": int(round(abs(weight) * 100)),
                "display": f"{weight:.1f}x",
            }
        )
    return dims


def parse_weight_form(raw: dict[str, str]) -> dict[str, float]:
    """Parse weight_<key> form fields into weight values."""
    weights: dict[str, float] = {}
    for key in _WEIGHT_LABELS:
        field = raw.get(f"weight_{key}")
        if field is None or field == "":
            continue
        magnitude = int(field) / 100.0
        weights[key] = -abs(magnitude) if key in _NEGATIVE_KEYS else abs(magnitude)
    return weights


def save_scoring_weights(
    weights: dict[str, float], db_path: str = "junk_detector.db"
) -> list[dict]:
    """Persist user weight overrides and return updated slider metadata."""
    from src.preferences.models import PreferencesUpdate, ScoringWeights
    from src.preferences.service import PreferencesService

    PreferencesService.update_preferences(
        WEB_USER_ID,
        PreferencesUpdate(scoring_weights=ScoringWeights(**weights)),
        db_path=db_path,
    )
    return get_scoring_weight_dims(db_path=db_path)


def reset_scoring_weights(db_path: str = "junk_detector.db") -> list[dict]:
    """Clear weight overrides so system defaults from config.yaml apply."""
    from src.preferences.models import ScoringWeights
    from src.preferences.service import PreferencesService

    prefs = PreferencesService.get_preferences(WEB_USER_ID, db_path=db_path)
    prefs.scoring_weights = ScoringWeights()
    PreferencesService.save_preferences(prefs, db_path=db_path)
    return get_scoring_weight_dims(db_path=db_path)


def build_web_scoring_config(db_path: str = "junk_detector.db"):
    """Scoring config for Web UI: user prefs + adaptive feedback adjustments."""
    from src.core.adaptive_weights import get_adjusted_weights
    from src.preferences.service import PreferencesService

    config = PreferencesService.build_scoring_config(WEB_USER_ID, db_path=db_path)
    adjusted = get_adjusted_weights(user_id="anonymous", base_weights=config.weights)
    if adjusted != config.weights:
        config = config.model_copy(deep=True)
        config.weights = adjusted
    return config
