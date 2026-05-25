"""Tests for configuration loading (src.core.config).

Verifies config.yaml parsing, env var overrides, and graceful defaults.
All file I/O is mocked.
"""
from __future__ import annotations

from unittest.mock import mock_open, patch

import pytest

from src.core.config import get_model_config, load_config
from src.models.score import ScoringConfig


class TestGetModelConfig:
    """Tests for get_model_config()."""

    @patch("src.core.config._load_yaml")
    def test_returns_preset_from_yaml(self, mock_yaml):
        """When config.yaml has a model preset, it returns those values."""
        mock_yaml.return_value = {
            "active_model": "openai",
            "models": {
                "openai": {
                    "primary": "gpt-4o",
                    "fallback": "gpt-4o-mini",
                }
            },
        }
        result = get_model_config()
        assert result["primary"] == "gpt-4o"
        assert result["fallback"] == "gpt-4o-mini"

    @patch("src.core.config._load_yaml")
    def test_returns_defaults_when_no_config(self, mock_yaml):
        """When no config file exists, returns default deepseek config."""
        mock_yaml.return_value = {}
        result = get_model_config()
        assert result["primary"] == "deepseek/deepseek-chat"
        assert result["fallback"] == "deepseek/deepseek-chat"

    @patch("src.core.config._load_yaml")
    def test_env_var_override(self, mock_yaml, monkeypatch):
        """JUNK_DETECTOR_MODEL env var overrides config.yaml active_model."""
        monkeypatch.setenv("JUNK_DETECTOR_MODEL", "openai")
        mock_yaml.return_value = {
            "active_model": "deepseek",
            "models": {
                "deepseek": {"primary": "deepseek/deepseek-chat", "fallback": "deepseek/deepseek-chat"},
                "openai": {"primary": "gpt-4o", "fallback": "gpt-4o-mini"},
            },
        }
        result = get_model_config()
        assert result["primary"] == "gpt-4o"

    @patch("src.core.config._load_yaml")
    def test_missing_preset_returns_defaults(self, mock_yaml):
        """When the active preset is not found in models, returns defaults."""
        mock_yaml.return_value = {
            "active_model": "nonexistent",
            "models": {},
        }
        result = get_model_config()
        assert result["primary"] == "deepseek/deepseek-chat"


class TestLoadConfig:
    """Tests for load_config()."""

    @patch("src.core.config._load_yaml")
    def test_load_config_with_scoring_section(self, mock_yaml):
        """load_config parses scoring weights and thresholds from yaml."""
        mock_yaml.return_value = {
            "active_model": "deepseek",
            "models": {
                "deepseek": {"primary": "deepseek/deepseek-chat", "fallback": "deepseek/deepseek-chat"},
            },
            "scoring": {
                "confidence_threshold": 0.8,
                "weights": {
                    "originality": 1.5,
                    "scam_prob": -1.5,
                },
            },
        }
        config = load_config()
        assert isinstance(config, ScoringConfig)
        assert config.confidence_threshold == 0.8
        assert config.weights["originality"] == 1.5

    @patch("src.core.config._load_yaml")
    def test_load_config_returns_defaults_gracefully(self, mock_yaml):
        """When no config file exists, returns ScoringConfig with defaults."""
        mock_yaml.return_value = {}
        config = load_config()
        assert isinstance(config, ScoringConfig)
        assert config.primary_model == "deepseek/deepseek-chat"
        assert config.confidence_threshold == 0.7
