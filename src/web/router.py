"""Backward-compat re-export."""

from src.web.routes import router
from src.web.routes.pages import _compute_stats

__all__ = ["router", "_compute_stats"]
