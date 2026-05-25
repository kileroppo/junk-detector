"""Tests for src/auth/router.py — auth API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.auth.models import Token, User


@pytest.fixture
def auth_client(set_api_key):
    """Create a TestClient for auth routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestRegisterEndpoint:
    """Tests for POST /auth/register."""

    def test_register_success(self, auth_client):
        """POST /auth/register creates a user and returns 200."""
        user = User(
            id=1,
            username="newuser",
            email="new@example.com",
            api_key="generated-key-123",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        with patch("src.auth.router.AuthService.register", return_value=user):
            response = auth_client.post(
                "/auth/register",
                json={"username": "newuser", "password": "pass123", "email": "new@example.com"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["username"] == "newuser"

    def test_register_duplicate_returns_409(self, auth_client):
        """POST /auth/register with duplicate username returns 409."""
        with patch(
            "src.auth.router.AuthService.register",
            side_effect=ValueError("Username 'bob' already exists"),
        ):
            response = auth_client.post(
                "/auth/register",
                json={"username": "bob", "password": "pass123"},
            )
            assert response.status_code == 409


class TestLoginEndpoint:
    """Tests for POST /auth/login."""

    def test_login_success(self, auth_client):
        """POST /auth/login with valid creds returns token."""
        token = Token(
            access_token="jwt-token-here",
            token_type="bearer",
            expires_at=datetime.now(timezone.utc),
        )
        with patch("src.auth.router.AuthService.login", return_value=token):
            response = auth_client.post(
                "/auth/login",
                json={"username": "user", "password": "pass"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["access_token"] == "jwt-token-here"

    def test_login_invalid_returns_401(self, auth_client):
        """POST /auth/login with invalid creds returns 401."""
        with patch(
            "src.auth.router.AuthService.login",
            side_effect=ValueError("Invalid username or password"),
        ):
            response = auth_client.post(
                "/auth/login",
                json={"username": "user", "password": "wrong"},
            )
            assert response.status_code == 401


class TestMeEndpoint:
    """Tests for GET /auth/me."""

    def test_me_authenticated(self, auth_client):
        """GET /auth/me returns user info when authenticated."""
        from src.api.app import app
        from src.auth.dependencies import get_current_user

        user = User(
            id=1,
            username="testuser",
            api_key="key",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            response = auth_client.get("/auth/me")
            assert response.status_code == 200
            assert response.json()["username"] == "testuser"
        finally:
            app.dependency_overrides.clear()


class TestRegenerateKeyEndpoint:
    """Tests for POST /auth/regenerate-key."""

    def test_regenerate_key_success(self, auth_client):
        """POST /auth/regenerate-key returns new key."""
        from src.api.app import app
        from src.auth.dependencies import get_current_user

        user = User(
            id=1,
            username="testuser",
            api_key="old-key",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            with patch(
                "src.auth.router.AuthService.regenerate_api_key", return_value="new-key-123"
            ):
                with patch("src.auth.router.AuthService.get_user_by_id", return_value=user):
                    response = auth_client.post("/auth/regenerate-key")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["api_key"] == "new-key-123"
        finally:
            app.dependency_overrides.clear()
