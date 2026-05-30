"""Scoring mode preset tests."""

from __future__ import annotations

from src.core.config import load_config
from src.core.scoring_modes import MODE_SCAM_GUARD, apply_scoring_mode


def test_scam_guard_increases_scam_weight():
    config = load_config()
    adjusted = apply_scoring_mode(config, MODE_SCAM_GUARD)
    assert abs(adjusted.weights["scam_prob"]) > abs(config.weights["scam_prob"])
