"""
Tests for extension UX enhancement features (Rounds 73-100).

Validates that the expected patterns, function names, and storage keys
exist in the extension JavaScript/HTML/CSS files.
"""

import os
import pytest

EXTENSION_DIR = os.path.join(os.path.dirname(__file__), "..", "extension")


def read_ext_file(filename):
    """Read an extension file and return its content."""
    path = os.path.join(EXTENSION_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestCalmState:
    """Round 73: Calm state message and breathing animation."""

    def test_calm_state_icon_in_popup_js(self):
        content = read_ext_file("popup.js")
        # Calm state shows sparkle emoji (stored as unicode escape)
        assert "\\u2728" in content

    def test_calm_state_message_in_popup_js(self):
        content = read_ext_file("popup.js")
        # Message: "当前页面未发现异常" stored as unicode escapes
        assert "\\u5f53\\u524d\\u9875\\u9762\\u672a\\u53d1\\u73b0\\u5f02\\u5e38" in content

    def test_calm_state_class_in_popup_js(self):
        content = read_ext_file("popup.js")
        assert "calm-state" in content

    def test_breathing_animation_in_css(self):
        content = read_ext_file("popup.css")
        assert "@keyframes breathe" in content
        assert "breathing" in content

    def test_breathing_class_applied_in_js(self):
        content = read_ext_file("popup.js")
        assert "breathing" in content


class TestAccessibility:
    """Round 79: Accessibility improvements."""

    def test_aria_labels_in_popup_html(self):
        content = read_ext_file("popup.html")
        assert 'aria-label' in content
        assert "\u6253\u5f00\u83dc\u5355" in content  # HTML has actual Chinese chars
        assert "\u5ffd\u7565\u6b64\u6b21\u68c0\u6d4b" in content
        assert "\u5206\u4eab\u7ed3\u679c" in content
        assert "\u53cd\u9988\u7ed3\u679c\u4e0d\u51c6\u786e" in content
        assert "\u6807\u8bb0\u9875\u9762\u95ee\u9898\u8bcd" in content

    def test_role_status_in_popup_html(self):
        content = read_ext_file("popup.html")
        assert 'role="status"' in content

    def test_aria_live_in_popup_html(self):
        content = read_ext_file("popup.html")
        assert 'aria-live="polite"' in content

    def test_high_contrast_mode_in_css(self):
        content = read_ext_file("popup.css")
        assert "prefers-contrast: high" in content


class TestReadingTime:
    """Round 77: Reading time saved calculation."""

    def test_reading_time_element_in_html(self):
        content = read_ext_file("popup.html")
        assert "reading-time" in content

    def test_reading_time_function_in_js(self):
        content = read_ext_file("popup.js")
        assert "displayReadingTimeSaved" in content

    def test_reading_time_formula(self):
        """Verify the 3-minute multiplier is used."""
        content = read_ext_file("popup.js")
        assert "* 3" in content

    def test_reading_time_message(self):
        content = read_ext_file("popup.js")
        # Message stored as unicode escapes - check for key function pattern
        assert "minutesSaved" in content


class TestSilentMode:
    """Round 84: Silent mode toggle."""

    def test_silent_toggle_in_options_html(self):
        content = read_ext_file("options.html")
        assert "silent-toggle" in content
        assert "\u6682\u505c\u68c0\u6d4b" in content  # HTML has actual Chinese chars

    def test_silent_until_in_options_js(self):
        content = read_ext_file("options.js")
        assert "silent_until" in content

    def test_silent_until_in_content_js(self):
        content = read_ext_file("content.js")
        assert "silent_until" in content

    def test_silent_mode_30_minutes(self):
        """Verify 30-minute timeout calculation."""
        content = read_ext_file("options.js")
        assert "30 * 60 * 1000" in content

    def test_silent_mode_remaining_time_in_popup(self):
        """Verify popup shows remaining silent time."""
        content = read_ext_file("popup.js")
        assert "silent_until" in content
        assert "checkSilentMode" in content
        assert "remainingMin" in content

    def test_silent_mode_early_end_button(self):
        """Verify popup has early-end button for silent mode."""
        content = read_ext_file("popup.js")
        # Check for the early-end button text (unicode for "提前结束")
        assert "\\u63d0\\u524d\\u7ed3\\u675f" in content


class TestCustomKeywords:
    """Round 92: Custom keywords support."""

    def test_custom_keywords_textarea_in_options_html(self):
        content = read_ext_file("options.html")
        assert "custom-keywords" in content
        assert "\u81ea\u5b9a\u4e49\u5173\u952e\u8bcd" in content  # HTML has actual Chinese

    def test_custom_keywords_storage_key_in_options_js(self):
        content = read_ext_file("options.js")
        assert "custom_keywords" in content

    def test_custom_keywords_merged_in_rules_js(self):
        content = read_ext_file("rules.js")
        assert "customKeywords" in content
        assert "effectiveScamKeywords" in content

    def test_custom_keywords_read_in_background_js(self):
        content = read_ext_file("background.js")
        assert "custom_keywords" in content
        assert "customKeywords" in content


class TestDOMRescore:
    """Round 89: DOM mutation re-score indicator."""

    def test_rescore_indicator_in_content_js(self):
        content = read_ext_file("content.js")
        # "重新检测中..." stored as unicode escapes in JS
        assert "\\u91cd\\u65b0\\u68c0\\u6d4b\\u4e2d" in content

    def test_rescore_indicator_element_id(self):
        content = read_ext_file("content.js")
        assert "junk-detector-rescore" in content

    def test_rescore_indicator_removed_after_scoring(self):
        content = read_ext_file("content.js")
        assert "removeRescoringIndicator" in content


class TestUpdateNotification:
    """Round 95: Update notification overlay."""

    def test_update_notification_element_in_html(self):
        content = read_ext_file("popup.html")
        assert "update-notification" in content

    def test_update_check_in_popup_js(self):
        content = read_ext_file("popup.js")
        assert "checkUpdateNotification" in content
        assert "updated" in content

    def test_update_notification_auto_dismiss(self):
        content = read_ext_file("popup.js")
        # Should auto-dismiss after 5 seconds
        assert "5000" in content

    def test_update_stores_flag_in_background(self):
        content = read_ext_file("background.js")
        assert "updated" in content
        assert "previousVersion" in content


class TestTopSites:
    """Round 81: Top sites tracking."""

    def test_top_sites_in_background_js(self):
        content = read_ext_file("background.js")
        assert "top_sites" in content
        assert "updateTopSites" in content

    def test_top_sites_tracking_structure(self):
        content = read_ext_file("background.js")
        assert "totalScore" in content
        assert "count" in content

    def test_top_sites_display_in_popup_js(self):
        content = read_ext_file("popup.js")
        assert "top_sites" in content
        assert "displayTopSiteStat" in content
        # Check the function exists and references top domain display
        assert "topDomain" in content

    def test_top_sites_cap_50(self):
        """Verify top_sites is capped at 50 domains."""
        content = read_ext_file("background.js")
        assert "50" in content
        # Verify the cap logic pattern exists
        assert "keys.length > 50" in content or "length > 50" in content


class TestStreakCelebration:
    """Round 100: 7-day streak celebration."""

    def test_streak_celebrated_7_in_popup_js(self):
        content = read_ext_file("popup.js")
        assert "streak_celebrated_7" in content

    def test_streak_celebration_message(self):
        content = read_ext_file("popup.js")
        # "连续使用 7 天" stored as unicode escapes in JS
        assert "\\u8fde\\u7eed\\u4f7f\\u7528 7 \\u5929" in content

    def test_streak_celebration_element_in_html(self):
        content = read_ext_file("popup.html")
        assert "streak-celebration" in content

    def test_streak_auto_dismiss(self):
        content = read_ext_file("popup.js")
        # Should auto-dismiss after 6 seconds
        assert "6000" in content
