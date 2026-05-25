"""Tests for src/preferences/service.py — PreferencesService CRUD and scoring config."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.preferences.models import (
    LabelThresholds,
    PreferencesUpdate,
    ScoringWeights,
    UserPreferences,
)
from src.preferences.service import PreferencesService, init_db


class TestGetPreferences:
    """Tests for PreferencesService.get_preferences."""

    def test_returns_default_for_nonexistent_user(self, tmp_db_path):
        """Non-existent user gets default UserPreferences."""
        init_db(tmp_db_path)
        prefs = PreferencesService.get_preferences(user_id=999, db_path=tmp_db_path)

        assert prefs.user_id == 999
        assert prefs.language == "zh"
        assert prefs.preferred_model is None
        assert prefs.confidence_threshold is None
        assert prefs.scoring_weights == ScoringWeights()
        assert prefs.label_thresholds == LabelThresholds()

    def test_returns_saved_preferences(self, tmp_db_path):
        """After saving, get_preferences returns saved data."""
        init_db(tmp_db_path)
        prefs = UserPreferences(
            user_id=1,
            language="en",
            preferred_model="gpt-4",
            confidence_threshold=0.9,
        )
        PreferencesService.save_preferences(prefs, db_path=tmp_db_path)

        loaded = PreferencesService.get_preferences(user_id=1, db_path=tmp_db_path)
        assert loaded.user_id == 1
        assert loaded.language == "en"
        assert loaded.preferred_model == "gpt-4"
        assert loaded.confidence_threshold == 0.9


class TestSavePreferences:
    """Tests for PreferencesService.save_preferences."""

    def test_save_and_retrieve(self, tmp_db_path):
        """save_preferences upserts correctly."""
        init_db(tmp_db_path)
        prefs = UserPreferences(
            user_id=42,
            scoring_weights=ScoringWeights(originality=2.0),
            language="en",
        )
        saved = PreferencesService.save_preferences(prefs, db_path=tmp_db_path)
        assert saved.user_id == 42

        loaded = PreferencesService.get_preferences(user_id=42, db_path=tmp_db_path)
        assert loaded.scoring_weights.originality == 2.0
        assert loaded.language == "en"

    def test_save_upserts_existing(self, tmp_db_path):
        """Saving twice overwrites existing record."""
        init_db(tmp_db_path)
        prefs = UserPreferences(user_id=1, language="zh")
        PreferencesService.save_preferences(prefs, db_path=tmp_db_path)

        prefs.language = "en"
        PreferencesService.save_preferences(prefs, db_path=tmp_db_path)

        loaded = PreferencesService.get_preferences(user_id=1, db_path=tmp_db_path)
        assert loaded.language == "en"


class TestUpdatePreferences:
    """Tests for PreferencesService.update_preferences."""

    def test_merges_scoring_weights(self, tmp_db_path):
        """update_preferences merges scoring_weights correctly."""
        init_db(tmp_db_path)
        # Save initial prefs with one weight set
        initial = UserPreferences(
            user_id=1,
            scoring_weights=ScoringWeights(originality=2.0, info_density=1.5),
        )
        PreferencesService.save_preferences(initial, db_path=tmp_db_path)

        # Update only originality
        update = PreferencesUpdate(
            scoring_weights=ScoringWeights(originality=3.0)
        )
        result = PreferencesService.update_preferences(1, update, db_path=tmp_db_path)

        assert result.scoring_weights.originality == 3.0
        # info_density should be preserved
        assert result.scoring_weights.info_density == 1.5

    def test_merges_label_thresholds(self, tmp_db_path):
        """update_preferences merges label_thresholds correctly."""
        init_db(tmp_db_path)
        initial = UserPreferences(
            user_id=1,
            label_thresholds=LabelThresholds(ai_generated=80.0, scam=50.0),
        )
        PreferencesService.save_preferences(initial, db_path=tmp_db_path)

        update = PreferencesUpdate(
            label_thresholds=LabelThresholds(ai_generated=90.0)
        )
        result = PreferencesService.update_preferences(1, update, db_path=tmp_db_path)

        assert result.label_thresholds.ai_generated == 90.0
        # scam should be preserved
        assert result.label_thresholds.scam == 50.0

    def test_updates_language(self, tmp_db_path):
        """update_preferences updates language field."""
        init_db(tmp_db_path)
        initial = UserPreferences(user_id=1, language="zh")
        PreferencesService.save_preferences(initial, db_path=tmp_db_path)

        update = PreferencesUpdate(language="en")
        result = PreferencesService.update_preferences(1, update, db_path=tmp_db_path)

        assert result.language == "en"


class TestDeletePreferences:
    """Tests for PreferencesService.delete_preferences."""

    def test_delete_removes_record(self, tmp_db_path):
        """delete_preferences removes the record; get returns defaults after delete."""
        init_db(tmp_db_path)
        prefs = UserPreferences(user_id=1, language="en", preferred_model="gpt-4")
        PreferencesService.save_preferences(prefs, db_path=tmp_db_path)

        PreferencesService.delete_preferences(user_id=1, db_path=tmp_db_path)

        loaded = PreferencesService.get_preferences(user_id=1, db_path=tmp_db_path)
        # Should be defaults again
        assert loaded.language == "zh"
        assert loaded.preferred_model is None


class TestBuildScoringConfig:
    """Tests for PreferencesService.build_scoring_config."""

    def test_no_user_prefs_returns_system_defaults(self, tmp_db_path):
        """build_scoring_config with no user prefs returns system defaults."""
        init_db(tmp_db_path)
        mock_config = {
            "scoring": {
                "weights": {"originality": 1.0, "info_density": 1.0},
                "label_thresholds": {"可能AI生成": 70.0},
                "confidence_threshold": 0.7,
            },
            "models": {
                "deepseek": {
                    "primary": "deepseek/deepseek-chat",
                    "fallback": "deepseek/deepseek-chat",
                    "api_base": "https://api.deepseek.com",
                }
            },
            "active_model": "deepseek",
        }

        with patch("src.preferences.service._load_config_yaml", return_value=mock_config):
            config = PreferencesService.build_scoring_config(
                user_id=999, db_path=tmp_db_path
            )

        assert config.weights["originality"] == 1.0
        assert config.weights["info_density"] == 1.0
        assert config.primary_model == "deepseek/deepseek-chat"
        assert config.confidence_threshold == 0.7

    def test_user_overrides_merge_correctly(self, tmp_db_path):
        """build_scoring_config with user overrides merges correctly."""
        init_db(tmp_db_path)
        # Save user prefs with some overrides
        prefs = UserPreferences(
            user_id=1,
            scoring_weights=ScoringWeights(originality=2.5),
            preferred_model="gpt-4o",
            confidence_threshold=0.9,
        )
        PreferencesService.save_preferences(prefs, db_path=tmp_db_path)

        mock_config = {
            "scoring": {
                "weights": {"originality": 1.0, "info_density": 1.0},
                "label_thresholds": {"可能AI生成": 70.0},
                "confidence_threshold": 0.7,
            },
            "models": {
                "deepseek": {
                    "primary": "deepseek/deepseek-chat",
                    "fallback": "deepseek/deepseek-chat",
                }
            },
            "active_model": "deepseek",
        }

        with patch("src.preferences.service._load_config_yaml", return_value=mock_config):
            config = PreferencesService.build_scoring_config(
                user_id=1, db_path=tmp_db_path
            )

        # User override should win
        assert config.weights["originality"] == 2.5
        # System default for non-overridden field
        assert config.weights["info_density"] == 1.0
        # User preferred model
        assert config.primary_model == "gpt-4o"
        # User confidence threshold
        assert config.confidence_threshold == 0.9
