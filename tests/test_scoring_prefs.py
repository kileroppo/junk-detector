"""Tests for web scoring weight settings."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestScoringPrefs:
    def test_save_and_load_weights(self, tmp_path: Path):
        db_path = str(tmp_path / "test.db")
        from src.web.scoring_prefs import (
            get_scoring_weight_dims,
            reset_scoring_weights,
            save_scoring_weights,
        )

        dims = get_scoring_weight_dims(db_path=db_path)
        assert any(d["key"] == "originality" for d in dims)

        save_scoring_weights({"originality": 1.5, "scam_prob": -1.5}, db_path=db_path)
        updated = get_scoring_weight_dims(db_path=db_path)
        orig = next(d for d in updated if d["key"] == "originality")
        scam = next(d for d in updated if d["key"] == "scam_prob")
        assert orig["weight"] == 1.5
        assert scam["weight"] == -1.5

        reset_scoring_weights(db_path=db_path)
        reset_dims = get_scoring_weight_dims(db_path=db_path)
        orig2 = next(d for d in reset_dims if d["key"] == "originality")
        assert orig2["weight"] == 1.0

    def test_parse_weight_form(self):
        from src.web.scoring_prefs import parse_weight_form

        parsed = parse_weight_form(
            {
                "weight_originality": "150",
                "weight_scam_prob": "130",
            }
        )
        assert parsed["originality"] == 1.5
        assert parsed["scam_prob"] == -1.3
