"""Storage backend factory."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def get_storage_backend(config: dict | None = None):
    """Create and return the configured storage backend.

    Args:
        config: Optional config dict. If None, loads from config.yaml.

    Returns:
        StorageBackend instance (SQLiteBackend or PostgresBackend).
    """
    if config is None:
        config = _load_storage_config()

    backend_type = config.get("backend", "sqlite")

    if backend_type == "postgres":
        from src.storage.postgres_backend import PostgresBackend

        dsn = config.get("postgres", {}).get("dsn")
        if not dsn:
            # Build DSN from individual params
            pg = config.get("postgres", {})
            host = pg.get("host", "localhost")
            port = pg.get("port", 5432)
            dbname = pg.get("dbname", "junk_detector")
            user = pg.get("user", "postgres")
            password = pg.get("password", "")
            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        return PostgresBackend(dsn=dsn)
    else:
        from src.storage.sqlite_backend import SQLiteBackend

        db_path = config.get("sqlite", {}).get("path", "junk_detector.db")
        return SQLiteBackend(db_path=db_path)


def _load_storage_config() -> dict:
    """Load storage config from config.yaml."""
    try:
        config_path = Path(__file__).parent.parent.parent / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                full_config = yaml.safe_load(f)
                return full_config.get("storage", {})
    except Exception as e:
        logger.warning("Failed to load storage config: %s", e)
    return {}
