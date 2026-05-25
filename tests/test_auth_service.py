"""Tests for src/auth/service.py — AuthService registration, login, JWT, and API keys."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.auth.models import UserCreate, UserLogin
from src.auth.service import AuthService


@pytest.fixture(autouse=True)
def mock_bcrypt():
    """Mock passlib's CryptContext to avoid bcrypt version issues."""
    with patch("src.auth.service._pwd_context") as mock_ctx:
        mock_ctx.hash.return_value = "$2b$12$mockedhashvalue1234567890123456789012345678901234"
        mock_ctx.verify.side_effect = lambda password, hash_val: password == "securepass123"
        yield mock_ctx


@pytest.fixture
def auth_db(tmp_db_path):
    """Initialize auth db and return path."""
    AuthService.init_db(tmp_db_path)
    return tmp_db_path


@pytest.fixture
def registered_user(auth_db):
    """Register and return a user for tests that need an existing user."""
    user_create = UserCreate(username="testuser", password="securepass123", email="test@example.com")
    user = AuthService.register(user_create, auth_db)
    return user


class TestRegister:
    """Tests for AuthService.register."""

    def test_register_creates_user(self, auth_db):
        """register creates a new user with correct fields."""
        user_create = UserCreate(username="alice", password="pass123", email="alice@example.com")
        user = AuthService.register(user_create, auth_db)

        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.api_key is not None
        assert len(user.api_key) == 32  # uuid4().hex length
        assert user.is_active is True

    def test_register_duplicate_username_raises(self, auth_db):
        """register raises ValueError for duplicate username."""
        user_create = UserCreate(username="bob", password="pass123")
        AuthService.register(user_create, auth_db)

        with pytest.raises(ValueError, match="already exists"):
            AuthService.register(user_create, auth_db)


class TestLogin:
    """Tests for AuthService.login."""

    def test_login_returns_token(self, auth_db, registered_user):
        """login with valid creds returns Token."""
        creds = UserLogin(username="testuser", password="securepass123")
        token = AuthService.login(creds, auth_db)

        assert token.access_token is not None
        assert token.token_type == "bearer"
        assert token.expires_at is not None

    def test_login_invalid_password_raises(self, auth_db, registered_user):
        """login with wrong password raises ValueError."""
        creds = UserLogin(username="testuser", password="wrongpass")
        with pytest.raises(ValueError, match="Invalid username or password"):
            AuthService.login(creds, auth_db)

    def test_login_nonexistent_user_raises(self, auth_db):
        """login with unknown username raises ValueError."""
        creds = UserLogin(username="nobody", password="pass")
        with pytest.raises(ValueError, match="Invalid username or password"):
            AuthService.login(creds, auth_db)


class TestVerifyToken:
    """Tests for AuthService.verify_token."""

    def test_verify_valid_token(self, auth_db, registered_user):
        """verify_token with valid token returns user info."""
        creds = UserLogin(username="testuser", password="securepass123")
        token = AuthService.login(creds, auth_db)

        payload = AuthService.verify_token(token.access_token)
        assert payload["username"] == "testuser"
        assert payload["user_id"] == registered_user.id

    def test_verify_invalid_token_raises(self):
        """verify_token with invalid token raises ValueError."""
        with pytest.raises(ValueError, match="Invalid token"):
            AuthService.verify_token("invalid.token.here")


class TestVerifyApiKey:
    """Tests for AuthService.verify_api_key."""

    def test_verify_valid_api_key(self, auth_db, registered_user):
        """verify_api_key with valid key returns user."""
        user = AuthService.verify_api_key(registered_user.api_key, auth_db)

        assert user is not None
        assert user.username == "testuser"

    def test_verify_invalid_api_key(self, auth_db):
        """verify_api_key with invalid key returns None."""
        user = AuthService.verify_api_key("nonexistent-key", auth_db)
        assert user is None


class TestGetUserById:
    """Tests for AuthService.get_user_by_id."""

    def test_existing_user(self, auth_db, registered_user):
        """get_user_by_id returns user for valid id."""
        user = AuthService.get_user_by_id(registered_user.id, auth_db)

        assert user is not None
        assert user.username == "testuser"

    def test_nonexistent_user(self, auth_db):
        """get_user_by_id returns None for unknown id."""
        user = AuthService.get_user_by_id(9999, auth_db)
        assert user is None


class TestRegenerateApiKey:
    """Tests for AuthService.regenerate_api_key."""

    def test_regenerate_returns_new_key(self, auth_db, registered_user):
        """regenerate_api_key returns a new API key."""
        old_key = registered_user.api_key
        new_key = AuthService.regenerate_api_key(registered_user.id, auth_db)

        assert new_key != old_key
        assert len(new_key) == 32

    def test_regenerate_nonexistent_user_raises(self, auth_db):
        """regenerate_api_key raises ValueError for unknown user."""
        with pytest.raises(ValueError, match="not found"):
            AuthService.regenerate_api_key(9999, auth_db)
