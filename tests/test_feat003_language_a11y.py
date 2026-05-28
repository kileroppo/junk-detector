"""Tests for FEAT-003: Rounds 5-6 (Non-native Language + Accessibility).

Verify:
- monitor_stats.html contains title attributes on jargon headings
- result.html displays Chinese dimension labels (not raw English keys)
- base.html has: aria-expanded on mobile menu button, role="switch" on theme toggle,
  aria-live on toast container, role="navigation" on nav
- score_form.html has: role="tablist", role="tab" on buttons, role="tabpanel" on content divs
- history.html table th elements have scope="col"
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "web" / "templates"


class TestMonitorStatsTooltips:
    """Verify monitor_stats.html has title tooltips on jargon."""

    def test_thunder_has_title_tooltip(self):
        content = (TEMPLATE_DIR / "partials" / "monitor_stats.html").read_text()
        assert 'title="Thunder: 自动RSS抓取引擎"' in content

    def test_dispatcher_has_title_tooltip(self):
        content = (TEMPLATE_DIR / "partials" / "monitor_stats.html").read_text()
        assert 'title="Dispatcher: 异步评分任务队列"' in content

    def test_token_roi_has_title_tooltip(self):
        content = (TEMPLATE_DIR / "partials" / "monitor_stats.html").read_text()
        assert 'title="令牌投资回报率 - 每次API调用的价值"' in content

    def test_dedup_pool_has_title_tooltip(self):
        content = (TEMPLATE_DIR / "partials" / "monitor_stats.html").read_text()
        assert 'title="已抓取过的网址去重记录"' in content


class TestResultChineseDimensionLabels:
    """Verify result.html maps English dimension keys to Chinese labels."""

    def test_dim_labels_dict_defined(self):
        content = (TEMPLATE_DIR / "result.html").read_text()
        assert "'originality': '原创性'" in content
        assert "'info_density': '信息密度'" in content
        assert "'ai_generated_prob': 'AI生成概率'" in content

    def test_dim_labels_used_in_display(self):
        content = (TEMPLATE_DIR / "result.html").read_text()
        assert "dim_labels[dim] if dim in dim_labels else dim" in content

    @patch("src.storage.db.get_by_id")
    def test_rendered_result_shows_chinese_labels(self, mock_get, web_client):
        """When dimension_sources has English keys, rendered HTML shows Chinese."""
        mock_get.return_value = {
            "id": 1,
            "title": "Test Article",
            "overall_score": 75.0,
            "rule_score": 70.0,
            "llm_score": 75.0,
            "rules_fired": True,
            "summary": "Good article.",
            "labels": [],
            "dimensions": {
                "originality": 80,
                "info_density": 70,
                "reasoning_quality": 65,
                "readability": 75,
                "timeliness": 60,
                "ai_generated_prob": 20,
                "emotional_manipulation": 15,
                "advertorial_prob": 10,
                "scam_prob": 5,
            },
            "dimension_sources": {
                "originality": "rule",
                "ai_generated_prob": "llm",
            },
            "rule_hits": ["combo_scam_urgency"],
            "confidence": 0.85,
            "model_used": "test-model",
            "cost": 0.001,
            "scored_at": "2025-01-15T12:00:00",
            "source_url": None,
            "source_warning": None,
            "divergence_warning": False,
            "focus_guide": None,
            "content_hash": "abc123",
        }
        response = web_client.get("/result/1")
        html = response.text
        # The result page should render successfully and show Chinese dimension names
        # in the 9-dimension breakdown section (those are always shown)
        assert "原创性" in html
        assert "信息密度" in html


class TestBaseHtmlAccessibility:
    """Verify base.html has proper ARIA attributes."""

    def test_nav_has_role_navigation(self):
        content = (TEMPLATE_DIR / "base.html").read_text()
        assert 'role="navigation"' in content
        assert 'aria-label="主导航"' in content

    def test_main_has_role_main(self):
        content = (TEMPLATE_DIR / "base.html").read_text()
        assert 'role="main"' in content

    def test_footer_has_role_contentinfo(self):
        content = (TEMPLATE_DIR / "base.html").read_text()
        assert 'role="contentinfo"' in content

    def test_mobile_menu_button_has_aria_expanded(self):
        content = (TEMPLATE_DIR / "base.html").read_text()
        assert 'aria-expanded="false"' in content

    def test_toast_container_has_aria_live(self):
        content = (TEMPLATE_DIR / "base.html").read_text()
        assert 'aria-live="polite"' in content
        assert 'role="status"' in content

    def test_toggle_mobile_menu_function_exists(self):
        content = (TEMPLATE_DIR / "base.html").read_text()
        assert "function toggleMobileMenu()" in content


class TestScoreFormTabsAccessibility:
    """Verify score_form.html has proper ARIA tab roles."""

    def test_tablist_role_present(self):
        content = (TEMPLATE_DIR / "score_form.html").read_text()
        assert 'role="tablist"' in content
        assert 'aria-label="输入方式选择"' in content

    def test_tab_buttons_have_role_tab(self):
        content = (TEMPLATE_DIR / "score_form.html").read_text()
        assert 'role="tab"' in content
        assert 'aria-selected="true"' in content
        assert 'aria-controls="content-text"' in content
        assert 'aria-controls="content-url"' in content
        assert 'aria-controls="content-batch"' in content

    def test_tab_panels_have_role_tabpanel(self):
        content = (TEMPLATE_DIR / "score_form.html").read_text()
        assert 'role="tabpanel"' in content
        assert 'aria-labelledby="tab-text"' in content
        assert 'aria-labelledby="tab-url"' in content
        assert 'aria-labelledby="tab-batch"' in content

    def test_switch_tab_toggles_aria_selected(self):
        content = (TEMPLATE_DIR / "score_form.html").read_text()
        assert "setAttribute('aria-selected'" in content


class TestHistoryTableAccessibility:
    """Verify history.html table has accessibility improvements."""

    def test_th_elements_have_scope_col(self):
        content = (TEMPLATE_DIR / "history.html").read_text()
        assert 'scope="col"' in content

    def test_score_badges_have_aria_label(self):
        content = (TEMPLATE_DIR / "history.html").read_text()
        assert 'aria-label="评分' in content

    def test_clickable_rows_have_keyboard_access(self):
        content = (TEMPLATE_DIR / "history.html").read_text()
        assert 'role="link"' in content
        assert 'tabindex="0"' in content
        assert "onkeydown" in content


class TestSettingsAccessibility:
    """Verify settings.html has accessible controls."""

    def test_dimension_labels_have_title(self):
        """Weight sliders removed in Round 9. Settings still has theme toggle accessibility."""
        content = (TEMPLATE_DIR / "settings.html").read_text()
        # Weight sliders removed; verify core settings sections remain
        assert "模型配置" in content
        assert "外观" in content
        assert "关于" in content

    def test_theme_toggle_has_switch_role(self):
        content = (TEMPLATE_DIR / "settings.html").read_text()
        assert 'role="switch"' in content
        assert 'aria-checked' in content


class TestBatchTabHelperText:
    """Verify score_form.html batch tab has helper text for non-native users."""

    def test_batch_helper_text_present(self):
        content = (TEMPLATE_DIR / "score_form.html").read_text()
        assert "每行输入一个网址，支持 http:// 和 https:// 开头的链接" in content

    def test_drop_zone_has_click_hint(self):
        """Drop zone simplified in Round 9 to single line."""
        content = (TEMPLATE_DIR / "score_form.html").read_text()
        assert "或拖放文件到此处" in content
