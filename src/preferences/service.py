"""Preferences service — CRUD operations and scoring config builder."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from src.models.score import ScoringConfig
from src.preferences.models import (
    LabelThresholds,
    PreferencesUpdate,
    ScoringWeights,
    UserPreferences,
)

logger = logging.getLogger("preferences")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    preferences_json TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT
);
"""

_initialized_dbs: set[str] = set()


def _get_connection(db_path: str) -> sqlite3.Connection:
    """Create a thread-safe SQLite connection with row factory."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_initialized(db_path: str) -> None:
    """Lazy initialization: create table if not already done for this db_path."""
    if db_path not in _initialized_dbs:
        init_db(db_path)


def init_db(db_path: str = "junk_detector.db") -> None:
    """Create the user_preferences table if it does not exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    conn = _get_connection(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        _initialized_dbs.add(db_path)
    finally:
        conn.close()


def _load_config_yaml() -> dict:
    """Load config.yaml from project root, returning the parsed dict."""
    # Try several possible locations
    candidates = [
        Path("config.yaml"),
        Path(__file__).parent.parent.parent / "config.yaml",
    ]
    for path in candidates:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    logger.warning("config.yaml not found, using empty defaults")
    return {}


class PreferencesService:
    """Service for managing user preferences."""

    @staticmethod
    def get_preferences(
        user_id: int, db_path: str = "junk_detector.db"
    ) -> UserPreferences:
        """Fetch user preferences from DB.

        If no record exists, returns default UserPreferences with user_id set.

        Args:
            user_id: The user's ID.
            db_path: Path to the SQLite database file.

        Returns:
            UserPreferences instance.
        """
        _ensure_initialized(db_path)

        conn = _get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT preferences_json, created_at, updated_at FROM user_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()

            if row is None:
                # Return defaults
                now = datetime.now()
                return UserPreferences(
                    user_id=user_id, created_at=now, updated_at=now
                )

            data = json.loads(row["preferences_json"])
            data["user_id"] = user_id
            if row["created_at"]:
                data["created_at"] = row["created_at"]
            if row["updated_at"]:
                data["updated_at"] = row["updated_at"]

            return UserPreferences.model_validate(data)
        finally:
            conn.close()

    @staticmethod
    def save_preferences(
        prefs: UserPreferences, db_path: str = "junk_detector.db"
    ) -> UserPreferences:
        """Upsert user preferences into DB.

        Args:
            prefs: The UserPreferences to save.
            db_path: Path to the SQLite database file.

        Returns:
            The saved UserPreferences (with updated timestamp).
        """
        _ensure_initialized(db_path)

        now = datetime.now()
        prefs.updated_at = now

        # Serialize all fields except user_id and timestamps (stored separately)
        data = prefs.model_dump(exclude={"user_id", "created_at", "updated_at"})
        preferences_json = json.dumps(data, ensure_ascii=False, default=str)

        conn = _get_connection(db_path)
        try:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferences_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences_json = excluded.preferences_json,
                    updated_at = excluded.updated_at
                """,
                (
                    prefs.user_id,
                    preferences_json,
                    prefs.created_at.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return prefs

    @staticmethod
    def update_preferences(
        user_id: int,
        update: PreferencesUpdate,
        db_path: str = "junk_detector.db",
    ) -> UserPreferences:
        """Merge a partial update into existing preferences.

        Only non-None fields from the update are applied.

        Args:
            user_id: The user's ID.
            update: Partial update with fields to override.
            db_path: Path to the SQLite database file.

        Returns:
            The updated UserPreferences.
        """
        current = PreferencesService.get_preferences(user_id, db_path)

        # Merge update fields into current preferences
        update_data = update.model_dump(exclude_none=True)

        if "scoring_weights" in update_data:
            # Merge individual weight fields
            current_weights = current.scoring_weights.model_dump()
            for key, value in update_data["scoring_weights"].items():
                if value is not None:
                    current_weights[key] = value
            current.scoring_weights = ScoringWeights.model_validate(current_weights)

        if "label_thresholds" in update_data:
            # Merge individual threshold fields
            current_thresholds = current.label_thresholds.model_dump()
            for key, value in update_data["label_thresholds"].items():
                if value is not None:
                    current_thresholds[key] = value
            current.label_thresholds = LabelThresholds.model_validate(
                current_thresholds
            )

        if "monitored_sources" in update_data:
            current.monitored_sources = update.monitored_sources  # type: ignore[assignment]

        if "preferred_model" in update_data:
            current.preferred_model = update.preferred_model

        if "confidence_threshold" in update_data:
            current.confidence_threshold = update.confidence_threshold

        if "language" in update_data:
            current.language = update.language  # type: ignore[assignment]

        return PreferencesService.save_preferences(current, db_path)

    @staticmethod
    def delete_preferences(
        user_id: int, db_path: str = "junk_detector.db"
    ) -> None:
        """Delete user preferences (reset to defaults).

        Args:
            user_id: The user's ID.
            db_path: Path to the SQLite database file.
        """
        _ensure_initialized(db_path)

        conn = _get_connection(db_path)
        try:
            conn.execute(
                "DELETE FROM user_preferences WHERE user_id = ?", (user_id,)
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def build_scoring_config(
        user_id: int, db_path: str = "junk_detector.db"
    ) -> ScoringConfig:
        """Build a ScoringConfig by merging user prefs with system defaults.

        For each weight/threshold, if the user has set it (not None),
        use the user's value; otherwise use the system default from config.yaml.

        Args:
            user_id: The user's ID.
            db_path: Path to the SQLite database file.

        Returns:
            A ScoringConfig ready for the scoring pipeline.
        """
        prefs = PreferencesService.get_preferences(user_id, db_path)
        config_data = _load_config_yaml()

        scoring_cfg = config_data.get("scoring", {})
        models_cfg = config_data.get("models", {})
        active_model_key = config_data.get("active_model", "deepseek")
        active_model_cfg = models_cfg.get(active_model_key, {})

        # --- Weights: merge user overrides with system defaults ---
        system_weights = scoring_cfg.get("weights", {})
        user_weights = prefs.scoring_weights.model_dump()

        merged_weights: dict[str, float] = {}
        for dim, default_val in system_weights.items():
            user_val = user_weights.get(dim)
            if user_val is not None:
                merged_weights[dim] = user_val
            else:
                merged_weights[dim] = default_val

        # --- Label thresholds: merge ---
        system_thresholds = scoring_cfg.get("label_thresholds", {})
        user_thresholds = prefs.label_thresholds.model_dump()

        # Map user threshold fields to system threshold keys
        threshold_mapping = {
            "ai_generated": "可能AI生成",
            "emotional_manipulation": "情绪操纵",
            "advertorial": "疑似软文",
            "scam": "疑似骗局",
            "high_quality": "高质量原创",
            "info_dense": "信息密度高",
        }

        merged_thresholds: dict[str, float] = dict(system_thresholds)
        for user_key, system_key in threshold_mapping.items():
            user_val = user_thresholds.get(user_key)
            if user_val is not None:
                merged_thresholds[system_key] = user_val

        # --- Model selection ---
        primary_model = (
            prefs.preferred_model
            if prefs.preferred_model
            else active_model_cfg.get("primary", "deepseek/deepseek-chat")
        )
        fallback_model = active_model_cfg.get(
            "fallback", "deepseek/deepseek-chat"
        )

        # --- Confidence threshold ---
        confidence = (
            prefs.confidence_threshold
            if prefs.confidence_threshold is not None
            else scoring_cfg.get("confidence_threshold", 0.7)
        )

        # --- API base ---
        api_base = active_model_cfg.get("api_base")

        return ScoringConfig(
            weights=merged_weights,
            primary_model=primary_model,
            fallback_model=fallback_model,
            confidence_threshold=confidence,
            label_thresholds=merged_thresholds,
            api_base=api_base,
        )
