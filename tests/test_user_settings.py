"""Tests for user settings persistence."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestUserSettings:
    def test_save_and_load_llm_settings(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "src.core.user_settings._SETTINGS_FILE", tmp_path / "settings.json"
        )
        from src.core.user_settings import (
            get_llm_settings,
            get_llm_settings_display,
            save_llm_settings,
        )

        save_llm_settings(
            provider="deepseek",
            model="deepseek/deepseek-chat",
            api_base="https://api.deepseek.com",
            api_key="sk-test-key-1234",
        )
        loaded = get_llm_settings()
        assert loaded["provider"] == "deepseek"
        assert loaded["api_key"] == "sk-test-key-1234"

        display = get_llm_settings_display()
        assert "sk-t" in display["api_key_masked"] or "••••" in display["api_key_masked"]
        assert display["configured"] is True

    def test_save_keeps_existing_api_key_when_blank(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "src.core.user_settings._SETTINGS_FILE", tmp_path / "settings.json"
        )
        from src.core.user_settings import get_llm_settings, save_llm_settings

        save_llm_settings(
            provider="openai",
            model="gpt-4o-mini",
            api_key="sk-original",
        )
        save_llm_settings(
            provider="openai",
            model="gpt-4o",
            api_key=None,
        )
        assert get_llm_settings()["api_key"] == "sk-original"
        assert get_llm_settings()["model"] == "gpt-4o"

    @patch("src.core.config._load_yaml")
    def test_get_model_config_uses_user_settings(self, mock_yaml, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "src.core.user_settings._SETTINGS_FILE", tmp_path / "settings.json"
        )
        from src.core.config import get_model_config
        from src.core.user_settings import save_llm_settings

        mock_yaml.return_value = {"active_model": "deepseek", "models": {}}
        save_llm_settings(
            provider="custom",
            model="gpt-4o-mini",
            api_base="https://relay.example.com/v1",
            api_key="sk-relay",
        )
        result = get_model_config()
        assert result["primary"] == "gpt-4o-mini"
        assert result["api_base"] == "https://relay.example.com/v1"
