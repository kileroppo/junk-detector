"""Tests for CSS animation features in the design system.

Verify that style.css contains expected animation classes,
accessibility features, and interaction patterns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CSS_PATH = Path(__file__).parent.parent / "src" / "web" / "static" / "style.css"


@pytest.fixture
def css_content():
    """Read the style.css file content."""
    return CSS_PATH.read_text(encoding="utf-8")


class TestAccessibilityAnimations:
    """Verify accessibility-related animation features."""

    def test_prefers_reduced_motion_media_query(self, css_content):
        """CSS includes prefers-reduced-motion media query."""
        assert "prefers-reduced-motion: reduce" in css_content

    def test_reduced_motion_disables_animations(self, css_content):
        """Reduced motion block disables animation duration."""
        assert "animation-duration: 0.01ms !important" in css_content

    def test_reduced_motion_disables_transitions(self, css_content):
        """Reduced motion block disables transition duration."""
        assert "transition-duration: 0.01ms !important" in css_content


class TestButtonInteractions:
    """Verify button micro-interaction CSS."""

    def test_button_active_scale(self, css_content):
        """Button active state includes scale(0.97) feedback."""
        assert "scale(0.97)" in css_content

    def test_button_focus_visible(self, css_content):
        """Button has focus-visible outline for keyboard users."""
        assert "focus-visible" in css_content


class TestCardInteractions:
    """Verify card interaction CSS."""

    def test_card_interactive_class_exists(self, css_content):
        """CSS includes .card-interactive class."""
        assert ".card-interactive" in css_content

    def test_card_hover_class_preserved(self, css_content):
        """Original .card-hover class is preserved."""
        assert ".card-hover" in css_content

    def test_card_interactive_spring_timing(self, css_content):
        """Card interactive uses spring timing function."""
        assert "var(--transition-spring)" in css_content


class TestStaggeredAnimations:
    """Verify staggered entrance animations."""

    def test_stagger_children_class(self, css_content):
        """CSS includes .stagger-children class."""
        assert ".stagger-children" in css_content

    def test_stagger_fade_in_keyframes(self, css_content):
        """CSS includes stagger-fade-in keyframes."""
        assert "@keyframes stagger-fade-in" in css_content

    def test_stagger_has_multiple_delays(self, css_content):
        """Stagger uses nth-child delays for sequential entrance."""
        assert "nth-child(1)" in css_content
        assert "nth-child(4)" in css_content


class TestScoreAnimations:
    """Verify score-related animations."""

    def test_score_value_animate_class(self, css_content):
        """CSS includes .score-value-animate class."""
        assert ".score-value-animate" in css_content

    def test_score_count_up_keyframes(self, css_content):
        """CSS includes score-count-up keyframes."""
        assert "@keyframes score-count-up" in css_content

    def test_score_ring_fill_preserved(self, css_content):
        """Original score-ring-fill animation is preserved."""
        assert "@keyframes score-ring-fill" in css_content


class TestToastAnimations:
    """Verify toast notification animations."""

    def test_toast_enter_with_cubic_bezier(self, css_content):
        """Toast enter uses spring cubic-bezier timing."""
        # Check toast-enter uses spring physics
        assert "toast-enter" in css_content
        assert "cubic-bezier(0.34, 1.56, 0.64, 1)" in css_content

    def test_toast_exit_animation(self, css_content):
        """Toast exit animation exists."""
        assert "@keyframes toast-exit" in css_content


class TestNavigationAnimations:
    """Verify navigation transition animations."""

    def test_nav_link_transition(self, css_content):
        """Nav links have smooth color/background transitions."""
        assert "nav a" in css_content

    def test_nav_underline_indicator(self, css_content):
        """Nav has animated underline indicator via ::after."""
        assert "nav a::after" in css_content


class TestScrollAnimations:
    """Verify scroll-related animations."""

    def test_smooth_scroll_behavior(self, css_content):
        """HTML has smooth scroll behavior."""
        assert "scroll-behavior: smooth" in css_content

    def test_animate_on_scroll_class(self, css_content):
        """CSS includes .animate-on-scroll class."""
        assert ".animate-on-scroll" in css_content

    def test_animate_on_scroll_visible(self, css_content):
        """CSS includes .animate-on-scroll.visible state."""
        assert ".animate-on-scroll.visible" in css_content
