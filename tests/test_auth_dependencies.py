"""Tests for src/auth/dependencies.py — authentication dependency functions."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.auth.dependencies import _extract_user, get_current_user, get_optional_user
from src.auth.models import User


@pytest.fixture
def mock_user():
    """Create a mock active user."""
    return User(
        id=1,
        username="testuser",
        api_key="valid-key",
        created_at=datetime.now(),
        is_active=True,
    )


def _make_request(
    auth_header=None,
    api_key_header=None,
    api_key_param=None,
):
    """Create a mock FastAPI Request object with given credentials."""
    request = MagicMock()
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header
    if api_key_header:
        headers["X-API-Key"] = api_key_header

    request.headers = MagicMock()
    request.headers.get = lambda key, default=None: headers.get(key, default)

    query_params = {}
    if api_key_param:
        query_params["api_key"] = api_key_param
    request.query_params = MagicMock()
    request.query_params.get = lambda key, default=None: query_params.get(key, default)

    return request


class TestExtractUser:
    """Tests for _extract_user internal function."""

    def test_bearer_token_valid(self, mock_user):
        """_extract_user extracts user from valid Bearer token."""
        request = _make_request(auth_header="Bearer valid-token")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_token.return_value = {"user_id": 1, "username": "testuser"}
            MockAuthService.get_user_by_id.return_value = mock_user

            user = _extract_user(request)
            assert user is not None
            assert user.username == "testuser"

    def test_bearer_token_invalid(self):
        """_extract_user returns None for invalid Bearer token."""
        request = _make_request(auth_header="Bearer invalid-token")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_token.side_effect = ValueError("Invalid token")

            user = _extract_user(request)
            assert user is None

    def test_api_key_header_valid(self, mock_user):
        """_extract_user extracts user from X-API-Key header."""
        request = _make_request(api_key_header="valid-key")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_api_key.return_value = mock_user

            user = _extract_user(request)
            assert user is not None
            assert user.username == "testuser"

    def test_api_key_header_invalid(self):
        """_extract_user returns None for invalid X-API-Key."""
        request = _make_request(api_key_header="bad-key")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_api_key.return_value = None

            user = _extract_user(request)
            assert user is None

    def test_api_key_query_param_valid(self, mock_user):
        """_extract_user extracts user from api_key query param."""
        request = _make_request(api_key_param="valid-key")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_api_key.return_value = mock_user

            user = _extract_user(request)
            assert user is not None

    def test_api_key_query_param_invalid(self):
        """_extract_user returns None for invalid api_key query param."""
        request = _make_request(api_key_param="bad-key")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_api_key.return_value = None

            user = _extract_user(request)
            assert user is None

    def test_no_credentials(self):
        """_extract_user returns None when no credentials provided."""
        request = _make_request()

        user = _extract_user(request)
        assert user is None


class TestGetCurrentUser:
    """Tests for get_current_user."""

    def test_raises_401_when_no_user(self):
        """get_current_user raises HTTPException 401 when not authenticated."""
        request = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(request)
        assert exc_info.value.status_code == 401

    def test_returns_user_when_authenticated(self, mock_user):
        """get_current_user returns user when credentials are valid."""
        request = _make_request(api_key_header="valid-key")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_api_key.return_value = mock_user

            user = get_current_user(request)
            assert user.username == "testuser"


class TestGetOptionalUser:
    """Tests for get_optional_user."""

    def test_returns_none_when_no_credentials(self):
        """get_optional_user returns None without raising."""
        request = _make_request()

        user = get_optional_user(request)
        assert user is None

    def test_returns_user_when_authenticated(self, mock_user):
        """get_optional_user returns user when credentials present."""
        request = _make_request(api_key_header="valid-key")

        with patch("src.auth.dependencies.AuthService") as MockAuthService:
            MockAuthService.verify_api_key.return_value = mock_user

            user = get_optional_user(request)
            assert user is not None
