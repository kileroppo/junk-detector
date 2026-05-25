"""Tests for src/core/platform_profiles.py — platform detection and weight overrides."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.platform_profiles import (
    apply_platform_weights,
    check_platform_extra_rules,
    detect_platform,
    get_platform_extra_rules,
    get_platform_profile,
)

MOCK_PLATFORM_DATA = {
    "platforms": {
        "wechat": {
            "domains": ["mp.weixin.qq.com", "weixin.qq.com"],
            "weight_overrides": {"advertorial_prob": -1.5},
            "extra_rules": ["\u5173\u6ce8\u516c\u4f17\u53f7", "\u70b9\u8d5e\u6536\u85cf"],
        },
        "zhihu": {
            "domains": ["zhihu.com"],
            "weight_overrides": {"reasoning_quality": 1.2},
            "extra_rules": [],
        },
        "default": {
            "weight_overrides": {},
            "extra_rules": [],
        },
    }
}


@pytest.fixture(autouse=True)
def mock_platform_configs():
    """Mock _load_yaml to return test platform data for all tests in this module."""
    with patch("src.core.config._load_yaml", return_value=MOCK_PLATFORM_DATA):
        yield


class TestDetectPlatform:
    """Tests for detect_platform."""

    def test_wechat_url(self):
        """detect_platform with weixin URL returns 'wechat'."""
        result = detect_platform("https://mp.weixin.qq.com/s/abc123")
        assert result == "wechat"

    def test_zhihu_url(self):
        """detect_platform with zhihu URL returns 'zhihu'."""
        result = detect_platform("https://zhihu.com/question/123")
        assert result == "zhihu"

    def test_unknown_url_returns_default(self):
        """detect_platform with unknown URL returns 'default'."""
        result = detect_platform("https://unknown.com/page")
        assert result == "default"

    def test_none_returns_default(self):
        """detect_platform(None) returns 'default'."""
        result = detect_platform(None)
        assert result == "default"

    def test_empty_string_returns_default(self):
        """detect_platform('') returns 'default'."""
        result = detect_platform("")
        assert result == "default"

    def test_subdomain_match(self):
        """detect_platform matches subdomains correctly."""
        result = detect_platform("https://www.zhihu.com/answer/456")
        assert result == "zhihu"


class TestApplyPlatformWeights:
    """Tests for apply_platform_weights."""

    def test_wechat_overrides_advertorial_prob(self):
        """apply_platform_weights merges wechat overrides correctly."""
        base_weights = {"originality": 1.0, "advertorial_prob": -1.0}
        result = apply_platform_weights(base_weights, "wechat")

        assert result["advertorial_prob"] == -1.5
        assert result["originality"] == 1.0

    def test_default_returns_base_unchanged(self):
        """apply_platform_weights with 'default' returns base_weights unchanged."""
        base_weights = {"originality": 1.0, "advertorial_prob": -1.0}
        result = apply_platform_weights(base_weights, "default")

        assert result == base_weights

    def test_does_not_mutate_base_weights(self):
        """apply_platform_weights does not mutate the original base_weights dict."""
        base_weights = {"originality": 1.0, "advertorial_prob": -1.0}
        apply_platform_weights(base_weights, "wechat")

        assert base_weights["advertorial_prob"] == -1.0


class TestCheckPlatformExtraRules:
    """Tests for check_platform_extra_rules."""

    def test_finds_keywords_in_content(self):
        """check_platform_extra_rules finds matched keywords."""
        content = "\u8bf7\u5173\u6ce8\u516c\u4f17\u53f7\u83b7\u53d6\u66f4\u591a"
        result = check_platform_extra_rules(content, "wechat")

        assert "\u5173\u6ce8\u516c\u4f17\u53f7" in result

    def test_no_match_returns_empty(self):
        """check_platform_extra_rules returns [] for content without keywords."""
        result = check_platform_extra_rules("normal content", "wechat")

        assert result == []

    def test_default_platform_returns_empty(self):
        """check_platform_extra_rules for 'default' returns []."""
        result = check_platform_extra_rules("any content", "default")

        assert result == []


class TestGetPlatformExtraRules:
    """Tests for get_platform_extra_rules."""

    def test_default_has_no_rules(self):
        """get_platform_extra_rules('default') returns []."""
        result = get_platform_extra_rules("default")
        assert result == []

    def test_wechat_has_rules(self):
        """get_platform_extra_rules('wechat') returns keywords list."""
        result = get_platform_extra_rules("wechat")
        assert len(result) == 2
        assert "\u5173\u6ce8\u516c\u4f17\u53f7" in result


class TestGetPlatformProfile:
    """Tests for get_platform_profile."""

    def test_known_platform(self):
        """get_platform_profile returns weight_overrides and extra_rules."""
        profile = get_platform_profile("wechat")

        assert "weight_overrides" in profile
        assert "extra_rules" in profile
        assert profile["weight_overrides"]["advertorial_prob"] == -1.5

    def test_unknown_platform_returns_default(self):
        """get_platform_profile for unknown platform returns default profile."""
        profile = get_platform_profile("nonexistent")

        assert profile["weight_overrides"] == {}
        assert profile["extra_rules"] == []
