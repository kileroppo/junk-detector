"""Tests for CLI --profile option."""
import pytest

from src.core.config import load_profile


class TestLoadProfile:
    """Tests for the load_profile() function."""

    def test_load_strict_profile(self):
        """strict profile should have threshold 50."""
        profile = load_profile("strict")
        assert profile["threshold"] == 50

    def test_load_standard_profile(self):
        """standard profile should have threshold 60."""
        profile = load_profile("standard")
        assert profile["threshold"] == 60

    def test_load_relaxed_profile(self):
        """relaxed profile should have threshold 75."""
        profile = load_profile("relaxed")
        assert profile["threshold"] == 75

    def test_invalid_profile_raises(self):
        """Unknown profile name should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            load_profile("nonexistent")

    def test_strict_has_scoring_overrides(self):
        """strict profile should have non-empty scoring_overrides."""
        profile = load_profile("strict")
        assert "scoring_overrides" in profile
        assert profile["scoring_overrides"].get("scam_prob") is not None

    def test_relaxed_has_lower_penalties(self):
        """relaxed profile should have less aggressive penalties."""
        strict = load_profile("strict")
        relaxed = load_profile("relaxed")
        # relaxed penalties should be less negative (closer to 0)
        assert relaxed["scoring_overrides"]["scam_prob"] > strict["scoring_overrides"]["scam_prob"]
