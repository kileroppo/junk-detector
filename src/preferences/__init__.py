"""User preferences — customizable scoring weights, sources, and thresholds."""
from src.preferences.models import UserPreferences, PreferencesUpdate
from src.preferences.service import PreferencesService

__all__ = ["UserPreferences", "PreferencesUpdate", "PreferencesService"]
