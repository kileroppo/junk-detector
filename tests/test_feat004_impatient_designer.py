"""Tests for FEAT-004: Rounds 7-8 (Extremely Impatient Person + Perfectionist Designer)."""

import pytest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "web" / "templates"


def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


class TestRound7SkeletonLoading:
    """Round 7: Verify skeleton loading states replace spinners."""

    def test_dashboard_has_skeleton_loading(self):
        content = _read_template("dashboard.html")
        assert "skeleton h-10" in content
        assert "skeleton" in content
        # Should NOT have the old spinner loading
        assert '<span class="spinner"></span>' not in content or "recent-scores" not in content.split('<span class="spinner"></span>')[0][-200:]

    def test_monitor_has_skeleton_loading(self):
        content = _read_template("monitor.html")
        assert "skeleton h-24 rounded-xl" in content
        assert "skeleton h-48 rounded-xl" in content
        # Old spinner-based loading should be gone from monitor-stats-container
        assert "加载监控数据..." not in content

    def test_score_form_has_progress_stages_indicator(self):
        content = _read_template("score_form.html")
        assert "scoring-progress-stages" in content
        assert "scoring-progress-inline" in content
        # Check all three stages are present
        assert "规则检测" in content
        assert "AI 分析" in content
        assert "生成结果" in content

    def test_score_form_has_hx_disabled_elt(self):
        content = _read_template("score_form.html")
        assert 'hx-disabled-elt="find button[type=submit]"' in content


class TestRound8PaddingConsistency:
    """Round 8: Verify consistent card padding across templates."""

    def test_result_card_containers_use_p5(self):
        content = _read_template("result.html")
        # The main score card and dimension breakdown should use p-5
        assert "rounded-xl p-5 border border-navy-700 text-center" in content
        assert "rounded-xl p-5 border border-navy-700 detail-section" in content
        # Should NOT have p-6 on card containers
        lines_with_p6 = [
            line for line in content.splitlines()
            if "p-6" in line and "bg-surface" in line and "rounded-xl" in line
        ]
        assert len(lines_with_p6) == 0, f"Found p-6 on card containers: {lines_with_p6}"

    def test_settings_card_containers_use_p5(self):
        content = _read_template("settings.html")
        # All card sections should use p-5
        lines_with_p6 = [
            line.strip() for line in content.splitlines()
            if "p-6" in line and "rounded-xl" in line and "border" in line
        ]
        assert len(lines_with_p6) == 0, f"Found p-6 on card containers: {lines_with_p6}"
        # Should have p-5 on card containers
        assert "rounded-xl p-5 border" in content

    def test_monitor_feeds_section_uses_p5(self):
        content = _read_template("monitor.html")
        assert "rounded-xl p-5 border border-navy-700" in content


class TestRound8BorderRadiusConsistency:
    """Round 8: Verify border-radius hierarchy."""

    def test_batch_drop_zone_uses_rounded_xl(self):
        content = _read_template("score_form.html")
        # The batch drop zone should use rounded-xl (card-level element)
        assert "batch-drop-zone" in content
        # Find the drop zone section (id and class may be on separate lines)
        idx = content.find("batch-drop-zone")
        # Check the surrounding 300 chars for rounded-xl
        snippet = content[idx : idx + 300]
        assert "rounded-xl" in snippet

    def test_history_filter_bar_uses_rounded_xl(self):
        content = _read_template("history.html")
        # The filter bar container should use rounded-xl
        filter_section = content.split("<!-- Filter Bar -->")[1].split("</form>")[0]
        assert "rounded-xl" in filter_section


class TestRound8NavAlignment:
    """Round 8: Verify nav items have consistent vertical alignment."""

    def test_nav_buttons_consistent_py2(self):
        content = _read_template("base.html")
        # Simple mode and font size buttons should use py-2 (same as nav links)
        assert 'id="simple-mode-btn"' in content
        simple_btn_line = [
            line for line in content.splitlines()
            if "simple-mode-btn" in line
        ]
        assert any("py-2" in line for line in simple_btn_line)

        font_btn_line = [
            line for line in content.splitlines()
            if "font-size-btn" in line
        ]
        assert any("py-2" in line for line in font_btn_line)


class TestRound8ScoreRingAlignment:
    """Round 8: Score ring alignment on narrow viewports."""

    def test_score_ring_containers_responsive_width(self):
        content = _read_template("result.html")
        # Score ring containers should have w-full sm:w-auto for clean stacking
        assert "w-full sm:w-auto" in content
