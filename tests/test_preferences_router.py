"""Tests for src/preferences/router.py — preferences API endpoints."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.auth.models import User
from src.preferences.models import MonitoredSource, UserPreferences


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    return User(
        id=1,
        username="testuser",
        api_key="test-api-key",
        created_at=datetime.now(),
        is_active=True,
    )


@pytest.fixture
def client(set_api_key, mock_user):
    """Create a TestClient with mocked auth dependency and no rate limiting."""
    from src.api.app import app
    from src.auth.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = lambda: mock_user

    with patch("src.api.rate_limit._should_rate_limit", return_value=False):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


class TestPreferencesEndpoints:
    """Tests for preferences router endpoints."""

    def test_get_preferences_default(self, client, mock_user):
        """GET /preferences returns default prefs for new user."""
        with patch(
            "src.preferences.router.PreferencesService.get_preferences",
            return_value=UserPreferences(user_id=1),
        ):
            response = client.get("/preferences")
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == 1
            assert data["language"] == "zh"

    def test_delete_preferences(self, client, mock_user):
        """DELETE /preferences resets to defaults."""
        with patch(
            "src.preferences.router.PreferencesService.delete_preferences"
        ) as mock_delete:
            response = client.delete("/preferences")
            assert response.status_code == 200
            assert response.json()["detail"] == "Preferences reset to defaults"
            mock_delete.assert_called_once_with(1)

    def test_patch_preferences(self, client, mock_user):
        """PATCH /preferences updates partial fields."""
        updated = UserPreferences(user_id=1, language="en")
        with patch(
            "src.preferences.router.PreferencesService.update_preferences",
            return_value=updated,
        ):
            response = client.patch(
                "/preferences",
                json={"language": "en"},
            )
            assert response.status_code == 200
            assert response.json()["language"] == "en"

    def test_put_preferences(self, client, mock_user):
        """PUT /preferences replaces all prefs."""
        new_prefs = UserPreferences(user_id=1, language="en", confidence_threshold=0.8)
        with patch(
            "src.preferences.router.PreferencesService.save_preferences",
            return_value=new_prefs,
        ):
            response = client.put(
                "/preferences",
                json=new_prefs.model_dump(mode="json"),
            )
            assert response.status_code == 200

    def test_get_sources_empty(self, client, mock_user):
        """GET /preferences/sources returns empty list by default."""
        with patch(
            "src.preferences.router.PreferencesService.get_preferences",
            return_value=UserPreferences(user_id=1),
        ):
            response = client.get("/preferences/sources")
            assert response.status_code == 200
            assert response.json() == []

    def test_add_source(self, client, mock_user):
        """POST /preferences/sources adds a new source."""
        prefs = UserPreferences(user_id=1)
        with patch(
            "src.preferences.router.PreferencesService.get_preferences",
            return_value=prefs,
        ):
            with patch(
                "src.preferences.router.PreferencesService.save_preferences",
                return_value=prefs,
            ):
                response = client.post(
                    "/preferences/sources",
                    json={
                        "name": "my-feed",
                        "type": "rss",
                        "url": "https://example.com/feed",
                    },
                )
                assert response.status_code == 201

    def test_add_duplicate_source_returns_409(self, client, mock_user):
        """POST /preferences/sources with duplicate name returns 409."""
        existing = MonitoredSource(name="my-feed", type="rss", url="https://example.com/feed")
        prefs = UserPreferences(user_id=1, monitored_sources=[existing])
        with patch(
            "src.preferences.router.PreferencesService.get_preferences",
            return_value=prefs,
        ):
            response = client.post(
                "/preferences/sources",
                json={
                    "name": "my-feed",
                    "type": "rss",
                    "url": "https://other.com/feed",
                },
            )
            assert response.status_code == 409

    def test_delete_source(self, client, mock_user):
        """DELETE /preferences/sources/{name} removes a source."""
        existing = MonitoredSource(name="my-feed", type="rss", url="https://example.com/feed")
        prefs = UserPreferences(user_id=1, monitored_sources=[existing])
        with patch(
            "src.preferences.router.PreferencesService.get_preferences",
            return_value=prefs,
        ):
            with patch(
                "src.preferences.router.PreferencesService.save_preferences",
                return_value=prefs,
            ):
                response = client.delete("/preferences/sources/my-feed")
                assert response.status_code == 200

    def test_delete_nonexistent_source_returns_404(self, client, mock_user):
        """DELETE /preferences/sources/{name} returns 404 for unknown source."""
        prefs = UserPreferences(user_id=1, monitored_sources=[])
        with patch(
            "src.preferences.router.PreferencesService.get_preferences",
            return_value=prefs,
        ):
            response = client.delete("/preferences/sources/missing")
            assert response.status_code == 404
