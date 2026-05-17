"""Authentication service — handles registration, login, JWT, and API keys."""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from passlib.context import CryptContext

from src.auth.models import Token, User, UserCreate, UserLogin

logger = logging.getLogger("auth")

# JWT configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "junk-detector-dev-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRATION_HOURS = 24

# Password hashing
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    api_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);
"""

_initialized_dbs: set[str] = set()


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a thread-safe SQLite connection with row factory."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


class AuthService:
    """Authentication service with class-level methods for user management."""

    @classmethod
    def init_db(cls, db_path: str = "junk_detector.db") -> None:
        """Create the users table if it does not exist.

        Args:
            db_path: Path to the SQLite database file.
        """
        if db_path in _initialized_dbs:
            return

        conn = _get_connection(db_path)
        try:
            conn.execute(_CREATE_USERS_TABLE_SQL)
            conn.commit()
            _initialized_dbs.add(db_path)
            logger.info("Auth database initialized at %s", db_path)
        finally:
            conn.close()

    @classmethod
    def _ensure_initialized(cls, db_path: str) -> None:
        """Lazy initialization: create table if not already done for this db_path."""
        if db_path not in _initialized_dbs:
            cls.init_db(db_path)

    @classmethod
    def register(cls, user: UserCreate, db_path: str = "junk_detector.db") -> User:
        """Register a new user.

        Args:
            user: User registration data.
            db_path: Path to the SQLite database file.

        Returns:
            The created User object (without password).

        Raises:
            ValueError: If username already exists.
        """
        cls._ensure_initialized(db_path)

        password_hash = _pwd_context.hash(user.password)
        api_key = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc)

        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (username, password_hash, email, api_key, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (user.username, password_hash, user.email, api_key, created_at.isoformat()),
            )
            conn.commit()
            user_id = cursor.lastrowid
            logger.info("User registered: %s (id=%d)", user.username, user_id)

            return User(
                id=user_id,
                username=user.username,
                email=user.email,
                api_key=api_key,
                created_at=created_at,
                is_active=True,
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{user.username}' already exists")
        finally:
            conn.close()

    @classmethod
    def login(cls, creds: UserLogin, db_path: str = "junk_detector.db") -> Token:
        """Authenticate a user and return a JWT token.

        Args:
            creds: Login credentials (username, password).
            db_path: Path to the SQLite database file.

        Returns:
            Token object with access_token and expiration.

        Raises:
            ValueError: If credentials are invalid.
        """
        cls._ensure_initialized(db_path)

        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT id, username, password_hash, is_active FROM users WHERE username = ?",
                (creds.username,),
            )
            row = cursor.fetchone()

            if row is None:
                logger.warning("Login failed: user '%s' not found", creds.username)
                raise ValueError("Invalid username or password")

            if not row["is_active"]:
                logger.warning("Login failed: user '%s' is inactive", creds.username)
                raise ValueError("Account is inactive")

            if not _pwd_context.verify(creds.password, row["password_hash"]):
                logger.warning("Login failed: invalid password for '%s'", creds.username)
                raise ValueError("Invalid username or password")

            # Generate JWT
            expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRATION_HOURS)
            payload = {
                "sub": str(row["id"]),
                "username": row["username"],
                "exp": expires_at,
            }
            access_token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

            logger.info("User logged in: %s", creds.username)
            return Token(
                access_token=access_token,
                token_type="bearer",
                expires_at=expires_at,
            )
        finally:
            conn.close()

    @staticmethod
    def verify_token(token: str) -> dict:
        """Decode and verify a JWT token.

        Args:
            token: The JWT token string.

        Returns:
            Dictionary with user_id and username.

        Raises:
            ValueError: If token is invalid or expired.
        """
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = int(payload["sub"])
            username = payload["username"]
            return {"user_id": user_id, "username": username}
        except (pyjwt.PyJWTError, KeyError, ValueError) as e:
            raise ValueError(f"Invalid token: {e}")

    @classmethod
    def verify_api_key(cls, api_key: str, db_path: str = "junk_detector.db") -> User | None:
        """Look up a user by API key.

        Args:
            api_key: The API key to verify.
            db_path: Path to the SQLite database file.

        Returns:
            User object if found and active, None otherwise.
        """
        cls._ensure_initialized(db_path)

        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT id, username, email, api_key, created_at, is_active FROM users WHERE api_key = ?",
                (api_key,),
            )
            row = cursor.fetchone()

            if row is None or not row["is_active"]:
                return None

            return User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                api_key=row["api_key"],
                created_at=datetime.fromisoformat(row["created_at"]),
                is_active=bool(row["is_active"]),
            )
        finally:
            conn.close()

    @classmethod
    def get_user_by_id(cls, user_id: int, db_path: str = "junk_detector.db") -> User | None:
        """Fetch a user by their ID.

        Args:
            user_id: The user's database ID.
            db_path: Path to the SQLite database file.

        Returns:
            User object if found, None otherwise.
        """
        cls._ensure_initialized(db_path)

        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT id, username, email, api_key, created_at, is_active FROM users WHERE id = ?",
                (user_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return User(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                api_key=row["api_key"],
                created_at=datetime.fromisoformat(row["created_at"]),
                is_active=bool(row["is_active"]),
            )
        finally:
            conn.close()

    @classmethod
    def regenerate_api_key(cls, user_id: int, db_path: str = "junk_detector.db") -> str:
        """Generate a new API key for a user.

        Args:
            user_id: The user's database ID.
            db_path: Path to the SQLite database file.

        Returns:
            The new API key string.

        Raises:
            ValueError: If user not found.
        """
        cls._ensure_initialized(db_path)

        new_key = uuid.uuid4().hex
        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                "UPDATE users SET api_key = ? WHERE id = ?",
                (new_key, user_id),
            )
            conn.commit()

            if cursor.rowcount == 0:
                raise ValueError(f"User with id {user_id} not found")

            logger.info("API key regenerated for user_id=%d", user_id)
            return new_key
        finally:
            conn.close()
