"""Tests for FEAT-005: Rounds 9-10 (Steve Jobs + Competitor's User).

Validates:
- Nav simplified (no Compare link, no simple-mode button)
- Settings page no longer shows disabled weight sliders
- Result page has credibility passport card
- Result page has share button
- Score form has secondary link to /compare
- Result page does NOT contain keyword matches section
- Base template does NOT contain toggleSimpleMode function
"""

import pytest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "web" / "templates"


class TestRound9SteveJobs:
    """Round 9: Remove everything unnecessary."""

    def test_nav_no_compare_link_desktop(self):
        """Compare link should NOT be in the main desktop navigation."""
        base_html = (TEMPLATES_DIR / "base.html").read_text()
        # The desktop nav section is between 'hidden md:flex' and 'md:hidden'
        desktop_nav_start = base_html.find('class="hidden md:flex')
        desktop_nav_end = base_html.find("<!-- Mobile menu button -->")
        desktop_nav = base_html[desktop_nav_start:desktop_nav_end]
        assert 'href="/compare"' not in desktop_nav

    def test_nav_no_compare_link_mobile(self):
        """Compare link should NOT be in the mobile navigation."""
        base_html = (TEMPLATES_DIR / "base.html").read_text()
        mobile_nav_start = base_html.find('id="mobile-menu"')
        mobile_nav_end = base_html.find("</nav>")
        mobile_nav = base_html[mobile_nav_start:mobile_nav_end]
        assert 'href="/compare"' not in mobile_nav

    def test_nav_no_simple_mode_button(self):
        """Simple mode button should be removed from nav."""
        base_html = (TEMPLATES_DIR / "base.html").read_text()
        assert 'id="simple-mode-btn"' not in base_html

    def test_no_toggle_simple_mode_function(self):
        """toggleSimpleMode function should be removed from base.html."""
        base_html = (TEMPLATES_DIR / "base.html").read_text()
        assert "toggleSimpleMode" not in base_html

    def test_nav_keeps_monitor(self):
        """Monitor link should still be in the navigation."""
        base_html = (TEMPLATES_DIR / "base.html").read_text()
        assert 'href="/monitor-status"' in base_html

    def test_nav_has_five_main_items(self):
        """Nav should have 5 main items: Dashboard, Score, History, Monitor, Settings."""
        base_html = (TEMPLATES_DIR / "base.html").read_text()
        desktop_nav_start = base_html.find('class="hidden md:flex')
        desktop_nav_end = base_html.find("<!-- Mobile menu button -->")
        desktop_nav = base_html[desktop_nav_start:desktop_nav_end]
        assert 'href="/dashboard"' in desktop_nav
        assert 'href="/score-form"' in desktop_nav
        assert 'href="/history-page"' in desktop_nav
        assert 'href="/monitor-status"' in desktop_nav
        assert 'href="/settings"' in desktop_nav

    def test_settings_no_weight_sliders(self):
        """Settings page should NOT contain disabled weight sliders."""
        settings_html = (TEMPLATES_DIR / "settings.html").read_text()
        assert "权重调整" not in settings_html
        assert "评分权重" not in settings_html
        assert 'type="range"' not in settings_html

    def test_result_no_keyword_matches_section(self):
        """Result page should NOT contain the keyword matches section."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "关键词匹配" not in result_html

    def test_result_no_simple_only_section(self):
        """Result page should not have simple-only hidden section."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert 'class="simple-only"' not in result_html

    def test_result_no_simple_hidden_class(self):
        """Result page should not use simple-hidden class."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "simple-hidden" not in result_html

    def test_result_no_detail_section_class(self):
        """Result page should not use detail-section class."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "detail-section" not in result_html

    def test_batch_drop_zone_simplified(self):
        """Batch drop zone should be a single-line element."""
        score_form_html = (TEMPLATES_DIR / "score_form.html").read_text()
        assert 'id="batch-drop-zone"' in score_form_html
        # Should not have the large SVG icon
        drop_start = score_form_html.find('id="batch-drop-zone"')
        drop_end = score_form_html.find("</div>", drop_start)
        drop_zone = score_form_html[drop_start:drop_end]
        assert "<svg" not in drop_zone
        assert "或拖放文件到此处" in drop_zone


class TestRound10CompetitorUser:
    """Round 10: Not worse than Notion/Readwise, has unique highlights."""

    def test_credibility_passport_exists(self):
        """Result page should have a credibility passport card."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert 'id="credibility-passport"' in result_html

    def test_credibility_passport_has_three_levels(self):
        """Credibility passport should have three verdict levels."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "可信赖" in result_html
        assert "谨慎参考" in result_html
        assert "不推荐" in result_html

    def test_share_button_exists(self):
        """Result page should have a share/copy button."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "shareResult" in result_html
        assert "复制摘要" in result_html

    def test_share_copies_summary(self):
        """Share function should use clipboard API."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "navigator.clipboard.writeText" in result_html

    def test_score_again_button(self):
        """Result page should have a 'score new content' button."""
        result_html = (TEMPLATES_DIR / "result.html").read_text()
        assert "评分新内容" in result_html
        assert 'href="/score-form"' in result_html

    def test_score_form_has_compare_link(self):
        """Score form should have a secondary link to /compare."""
        score_form_html = (TEMPLATES_DIR / "score_form.html").read_text()
        assert 'href="/compare"' in score_form_html
        assert "打开对比模式" in score_form_html

    def test_compare_route_still_accessible(self):
        """The /compare page itself must still exist in routes."""
        pages_py = (Path(__file__).parent.parent / "src" / "web" / "routes" / "pages.py").read_text()
        assert "/compare" in pages_py


class TestIterateSkillOutput:
    """Verify the iterate skill markdown was created."""

    def test_iterate_round_9_10_md_exists(self):
        """The iterate round 9-10 markdown file should exist."""
        md_path = TEMPLATES_DIR / "partials" / "iterate_round_9_10.md"
        assert md_path.exists()

    def test_iterate_md_has_round_9_content(self):
        """Markdown should contain Round 9 content."""
        md_path = TEMPLATES_DIR / "partials" / "iterate_round_9_10.md"
        content = md_path.read_text()
        assert "Steve Jobs" in content
        assert "少则得" in content

    def test_iterate_md_has_round_10_content(self):
        """Markdown should contain Round 10 content."""
        md_path = TEMPLATES_DIR / "partials" / "iterate_round_9_10.md"
        content = md_path.read_text()
        assert "Competitor" in content
        assert "知人者智" in content
