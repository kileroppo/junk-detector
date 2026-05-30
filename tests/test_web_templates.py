"""Tests for web template content validation.

Verify that rendered templates contain expected structural elements,
navigation links, and content sections.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_client(set_api_key):
    """Create a TestClient for web routes."""
    from src.api.app import app

    with TestClient(app) as c:
        yield c


class TestDashboardTemplateContent:
    """Verify dashboard HTML contains expected structural elements."""

    @patch("src.web.router.get_history")
    def test_dashboard_has_stat_cards(self, mock_history, web_client):
        """Dashboard contains summary stat cards."""
        mock_history.return_value = [
            {"overall_score": 80.0},
            {"overall_score": 30.0},
        ]
        response = web_client.get("/dashboard")
        html = response.text

        # Stat card labels in Chinese
        assert "总评分数" in html
        assert "平均分数" in html
        assert "低质量内容" in html
        assert "高质量内容" in html

    @patch("src.web.router.get_history")
    def test_dashboard_has_quick_score_form(self, mock_history, web_client):
        """Dashboard contains quick score form."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert "快速评分" in html
        assert 'action="/score-submit"' in html
        assert 'method="post"' in html

    @patch("src.web.router.get_history")
    def test_dashboard_has_recent_scores_container(self, mock_history, web_client):
        """Dashboard has recent-scores container with HTMX polling."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert "recent-scores-container" in html
        assert 'hx-get="/partials/recent-scores"' in html
        assert "最近评分" in html


class TestScoreFormTemplateContent:
    """Verify score form HTML contains expected elements."""

    def test_score_form_has_text_tab(self, web_client):
        """Score form includes text tab."""
        response = web_client.get("/score-form")
        html = response.text

        assert "tab-text" in html
        assert 'name="text"' in html

    def test_score_form_has_url_tab(self, web_client):
        """Score form includes URL tab."""
        response = web_client.get("/score-form")
        html = response.text

        assert "tab-url" in html
        assert 'name="url"' in html

    def test_score_form_defaults_to_url_tab(self, web_client):
        """Score form opens on the URL tab by default."""
        response = web_client.get("/score-form")
        html = response.text

        assert 'id="content-url" class="tab-content active"' in html
        assert 'id="content-text" class="tab-content active"' not in html
        tab_idx = html.index('id="tab-url"')
        assert "tab-btn active" in html[tab_idx : tab_idx + 120]

    def test_score_form_has_hx_post(self, web_client):
        """Score form uses hx-post for HTMX submission."""
        response = web_client.get("/score-form")
        html = response.text

        assert 'hx-post="/score-submit"' in html

    def test_score_form_has_submit_button(self, web_client):
        """Score form contains submit button."""
        response = web_client.get("/score-form")
        html = response.text

        assert "开始评分" in html
        assert 'type="submit"' in html

    def test_score_form_has_hidden_input_type(self, web_client):
        """Score form has hidden input_type field."""
        response = web_client.get("/score-form")
        html = response.text

        assert 'name="input_type"' in html
        assert 'value="text"' in html
        assert 'value="url"' in html


class TestResultTemplateContent:
    """Verify result page HTML contains expected elements."""

    @patch("src.web.router.query")
    def test_result_has_score_display(self, mock_query, web_client):
        """Result page displays overall score in SVG ring."""
        mock_query.return_value = [
            {
                "id": 1,
                "overall_score": 72.5,
                "dimensions": {
                    "originality": 80,
                    "info_density": 70,
                    "reasoning_quality": 75,
                    "readability": 85,
                    "timeliness": 60,
                    "ai_generated_prob": 15,
                    "emotional_manipulation": 10,
                    "advertorial_prob": 20,
                    "scam_prob": 5,
                },
                "labels": [],
                "summary": "Good content",
                "model_used": "test-model",
                "cost": 0.001,
                "confidence": 0.9,
                "scored_at": "2024-01-01T12:00:00",
                "title": "Test Article",
                "source_url": "https://example.com",
            }
        ]
        response = web_client.get("/result/1")
        html = response.text

        # SVG score ring
        assert "<svg" in html
        assert "score-ring-circle" in html
        # Score value displayed
        assert "72" in html or "73" in html

    @patch("src.web.router.query")
    def test_result_has_dimension_bars(self, mock_query, web_client):
        """Result page shows dimension progress bars for all 9 dimensions."""
        mock_query.return_value = [
            {
                "id": 1,
                "overall_score": 72.5,
                "dimensions": {
                    "originality": 80,
                    "info_density": 70,
                    "reasoning_quality": 75,
                    "readability": 85,
                    "timeliness": 60,
                    "ai_generated_prob": 15,
                    "emotional_manipulation": 10,
                    "advertorial_prob": 20,
                    "scam_prob": 5,
                },
                "labels": ["高质量原创"],
                "summary": "Good content",
                "model_used": "test-model",
                "cost": 0.001,
                "confidence": 0.9,
                "scored_at": "2024-01-01T12:00:00",
                "title": "Test Article",
                "source_url": "https://example.com",
            }
        ]
        response = web_client.get("/result/1")
        html = response.text

        # Dimension labels in Chinese
        assert "原创性" in html
        assert "信息密度" in html
        assert "九维评分详情" in html
        assert "dimension-panel" in html
        assert "主要亮点" in html
        assert "dim-help" in html
        assert "是否有独特观点或第一手信息" in html

        # Dimension bar elements
        assert "dimension-bar" in html

    @patch("src.web.result_display.build_result_display_data_from_record")
    @patch("src.web.router.query")
    def test_result_has_sticky_bar_when_present(self, mock_query, mock_build_display, web_client):
        """Result page renders sticky summary bar when display data includes sticky_bar."""
        mock_query.return_value = [
            {
                "id": 1,
                "overall_score": 72.5,
                "dimensions": {
                    "originality": 80,
                    "info_density": 70,
                    "reasoning_quality": 75,
                    "readability": 85,
                    "timeliness": 60,
                    "ai_generated_prob": 15,
                    "emotional_manipulation": 10,
                    "advertorial_prob": 20,
                    "scam_prob": 5,
                },
                "labels": [],
                "summary": "Good content",
                "model_used": "test-model",
                "cost": 0.001,
                "confidence": 0.9,
                "scored_at": "2024-01-01T12:00:00",
                "title": "Test Article With A Very Long Title That Should Truncate In Sticky Bar",
                "source_url": "https://example.com",
            }
        ]
        mock_build_display.return_value = {
            "overall_score": 72.5,
            "primary_score": 72.5,
            "score_tier": {"key": "quality", "label": "质量良好", "css": "score-tier-quality"},
            "dimensions": mock_query.return_value[0]["dimensions"],
            "dimension_highlights": {"top_positive": [], "top_risks": []},
            "rule_hit_display": [],
            "labels": [],
            "summary": "Good content",
            "model_used": "test-model",
            "cost": 0.001,
            "confidence": 0.9,
            "scored_at": "2024-01-01T12:00:00",
            "title": mock_query.return_value[0]["title"],
            "source_url": "https://example.com",
            "focus_guide": None,
            "rule_hits": [],
            "dimension_sources": {},
            "rules_fired": False,
            "divergence_warning": False,
            "sticky_bar": {
                "title": "Test Article With A Very Long Title That Should Truncate In Sticky Bar",
                "verdict_label": "跳读即可",
                "verdict_css": "result-sticky-verdict--skim",
                "score": 73,
                "score_tier": {"label": "质量良好", "css": "score-tier-quality"},
                "copy_text": "跳读即可 · 73 分 · 质量良好",
                "source_url": "https://example.com",
            },
            "reading_verdict": {
                "headline": "整体质量良好",
                "detail": "未发现明显风险信号",
                "recommendation": "read_carefully",
            },
            "dimension_explanation": "主要亮点：原创性 80",
        }

        response = web_client.get("/result/1")
        html = response.text

        assert "result-sticky-bar" in html
        assert "result-sticky-bar-title" in html
        assert "result-sticky-bar-score" in html
        assert "73" in html
        assert "质量良好" in html
        assert "跳读即可" in html
        assert "result-sticky-actions" in html
        assert "整体质量良好" in html
        assert "主要亮点：原创性 80" in html


class TestHistoryTemplateContent:
    """Verify history page HTML contains filter form and table elements."""

    @patch("src.web.router.query")
    def test_history_has_filter_form(self, mock_query, web_client):
        """History page has filter form with expected inputs."""
        mock_query.return_value = []
        response = web_client.get("/history-page")
        html = response.text

        assert 'action="/history-page"' in html
        assert 'name="min_score"' in html
        assert 'name="label"' in html
        assert 'name="date_from"' in html
        assert "筛选" in html

    @patch("src.web.router.query")
    def test_history_has_table_headers(self, mock_query, web_client):
        """History page has table with proper column headers."""
        mock_query.return_value = [
            {
                "id": 1,
                "overall_score": 72.5,
                "labels": [],
                "summary": "Test summary",
                "scored_at": "2024-01-01T12:00:00",
                "title": "Test",
                "source_url": None,
            }
        ]
        response = web_client.get("/history-page")
        html = response.text

        # Table column headers
        assert "时间" in html
        assert "评分" in html
        assert "标签" in html
        assert "摘要" in html

    @patch("src.web.router.query")
    def test_history_empty_state(self, mock_query, web_client):
        """History page shows empty state when no results."""
        mock_query.return_value = []
        response = web_client.get("/history-page")
        html = response.text

        assert "暂无评分记录" in html


class TestSettingsTemplateContent:
    """Verify settings page HTML contains expected sections."""

    def test_settings_has_model_config(self, web_client):
        """Settings page contains model configuration section."""
        response = web_client.get("/settings")
        html = response.text

        assert "模型配置" in html
        assert "当前模型" in html
        assert "API Key" in html

    def test_settings_has_theme_toggle(self, web_client):
        """Theme toggle lives in the global nav (sun/moon), not settings page."""
        response = web_client.get("/dashboard")
        html = response.text

        assert "toggleTheme()" in html
        assert 'data-theme-toggle' in html
        assert 'data-theme-icon="sun"' in html
        assert 'data-theme-icon="moon"' in html
        assert "localStorage" in html

        settings = web_client.get("/settings")
        assert "外观" not in settings.text
        assert 'id="theme-toggle-knob"' not in settings.text

    def test_settings_has_scoring_preferences(self, web_client):
        """Settings page contains scoring weight preferences."""
        response = web_client.get("/settings")
        html = response.text

        assert "评分权重" in html
        assert "原创性" in html
        assert "信息密度" in html
        assert 'name="weight_originality"' in html
        assert "disabled" not in html.split("评分权重")[1].split("平台 Cookie")[0]


class TestBaseTemplateElements:
    """Verify base template elements appear across pages."""

    @patch("src.web.router.get_history")
    def test_navigation_links_present(self, mock_history, web_client):
        """All pages include navigation links to all sections."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        # Nav links
        assert 'href="/dashboard"' in html
        assert 'href="/score-form"' in html
        assert 'href="/history-page"' in html
        assert 'href="/monitor-status"' in html
        assert 'href="/settings"' in html

    @patch("src.web.router.get_history")
    def test_footer_present(self, mock_history, web_client):
        """All pages include footer."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert "Junk Detector v0.1" in html

    @patch("src.web.router.get_history")
    def test_theme_initialization_script(self, mock_history, web_client):
        """Base template includes theme initialization script to prevent FOUC."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        # Theme init script reads from localStorage and applies dark class
        assert "localStorage.getItem('theme')" in html or "localStorage.getItem(&#x27;theme&#x27;)" in html or "localStorage" in html
        assert "toggleTheme" in html
        assert 'darkMode' in html

    def test_settings_has_nav_and_footer(self, web_client):
        """Settings page also has nav and footer from base template."""
        response = web_client.get("/settings")
        html = response.text

        assert 'href="/dashboard"' in html
        assert "Junk Detector v0.1" in html
