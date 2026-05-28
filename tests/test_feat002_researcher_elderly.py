"""Tests for FEAT-002: Round 3 (Deep Researcher) & Round 4 (Retired Elderly)."""

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


# ---------------------------------------------------------------------------
# Round 3: Deep Researcher
# ---------------------------------------------------------------------------


class TestHistorySearchField:
    """History page accepts and displays search parameter."""

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_history_page_accepts_search_param(self, mock_query, mock_count, web_client):
        """The history page endpoint accepts a search query parameter."""
        mock_count.return_value = 0
        mock_query.return_value = []
        response = web_client.get("/history-page?search=test")
        assert response.status_code == 200

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_history_page_search_field_rendered(self, mock_query, mock_count, web_client):
        """The search input field is present in history page HTML."""
        mock_count.return_value = 0
        mock_query.return_value = []
        response = web_client.get("/history-page")
        assert response.status_code == 200
        html = response.text
        assert 'name="search"' in html
        assert "搜索标题或摘要..." in html

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_history_page_search_value_preserved(self, mock_query, mock_count, web_client):
        """The search value is preserved in the form after submission."""
        mock_count.return_value = 0
        mock_query.return_value = []
        response = web_client.get("/history-page?search=hello")
        assert response.status_code == 200
        html = response.text
        assert 'value="hello"' in html

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_history_page_search_passed_to_query(self, mock_query, mock_count, web_client):
        """The search param is passed to the query function as a filter."""
        mock_count.return_value = 0
        mock_query.return_value = []
        web_client.get("/history-page?search=myterm")
        # Verify the query function was called with search in filters
        call_kwargs = mock_query.call_args
        filters = call_kwargs[1].get("filters") if call_kwargs[1] else call_kwargs[0][0] if call_kwargs[0] else None
        # The filters dict or keyword arg should contain search
        if filters is None and call_kwargs[1]:
            filters = call_kwargs[1].get("filters")
        assert filters is not None
        assert filters.get("search") == "myterm"

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_pagination_shows_page_info(self, mock_query, mock_count, web_client):
        """Pagination shows position and total page count."""
        mock_count.return_value = 50
        mock_query.return_value = [
            {
                "id": i,
                "title": f"Article {i}",
                "source_url": None,
                "overall_score": 60.0,
                "labels": [],
                "summary": "Test summary",
                "scored_at": "2025-01-15T10:00:00",
                "content_hash": f"hash{i}",
            }
            for i in range(20)
        ]
        response = web_client.get("/history-page?page=2")
        html = response.text
        # Should show page N / M format
        assert "第 2 /" in html


class TestKeyboardShortcutSearch:
    """Keyboard shortcut 'S' is documented in the JS."""

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_search_shortcut_in_js(self, mock_query, mock_count, web_client):
        """The 'S' key shortcut for search focus is in the base template."""
        mock_count.return_value = 0
        mock_query.return_value = []
        response = web_client.get("/history-page")
        html = response.text
        assert "e.key === 's'" in html or "e.key === 'S'" in html
        assert 'input[name="search"]' in html

    @patch("src.web.routes.pages.count_records")
    @patch("src.web.routes.pages.query")
    def test_search_shortcut_documented_in_overlay(self, mock_query, mock_count, web_client):
        """The shortcut overlay documents the 'S' key."""
        mock_count.return_value = 0
        mock_query.return_value = []
        response = web_client.get("/history-page")
        html = response.text
        assert ">S<" in html
        assert "搜索历史" in html


# ---------------------------------------------------------------------------
# Round 4: Retired Elderly
# ---------------------------------------------------------------------------


class TestFontSizeToggle:
    """Font-size toggle button exists in base.html."""

    @patch("src.web.routes.pages.get_history")
    def test_font_size_toggle_button_exists(self, mock_history, web_client):
        """The font-size toggle button is present in rendered pages."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert 'id="font-size-btn"' in html
        assert "cycleFontSize()" in html

    @patch("src.web.routes.pages.get_history")
    def test_font_size_css_classes_defined(self, mock_history, web_client):
        """Font size CSS classes are in the inline style."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text
        assert "font-large" in html
        assert "font-xl" in html


class TestScoreRingAriaLabel:
    """Score ring SVGs have aria-label with score value."""

    def test_aria_label_in_result_template(self):
        """The result template source contains aria-label on SVGs."""
        template_path = Path("src/web/templates/result.html")
        content = template_path.read_text()
        assert 'aria-label="综合评分' in content

    @patch("src.storage.db.get_by_id")
    def test_single_score_ring_has_aria_label(self, mock_get_by_id, web_client):
        """The single score ring SVG has an aria-label when rendered."""
        mock_get_by_id.return_value = {
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
            "summary": "Test",
            "model_used": "test",
            "cost": 0,
            "confidence": 1.0,
            "scored_at": "2025-01-15T10:00:00",
            "title": "Test Article",
            "source_url": None,
        }
        response = web_client.get("/result/1")
        assert response.status_code == 200
        html = response.text
        assert 'aria-label="综合评分' in html


class TestFooterHelpButton:
    """Footer help button has w-11 h-11 classes."""

    @patch("src.web.routes.pages.get_history")
    def test_help_button_size(self, mock_history, web_client):
        """The footer ? button is 44px (w-11 h-11)."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text
        # The shortcut-help-btn should have w-11 h-11
        assert "w-11 h-11" in html

    @patch("src.web.routes.pages.get_history")
    def test_mobile_hamburger_touch_target(self, mock_history, web_client):
        """The mobile hamburger button meets 44px min touch target."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text
        assert "min-w-[44px]" in html
        assert "min-h-[44px]" in html


class TestContrastFixes:
    """Readable content text uses text-gray-400 instead of text-gray-500."""

    def test_score_form_helper_text_contrast(self, web_client):
        """Score form helper text uses text-gray-400 for readability."""
        response = web_client.get("/score-form")
        html = response.text
        lines = html.split("\n")
        for line in lines:
            if "Ctrl+Enter" in line:
                assert "text-gray-400" in line
                break
        else:
            pytest.fail("Ctrl+Enter text not found in score_form page")

    def test_monitor_description_contrast(self, web_client):
        """Monitor page description uses text-gray-400."""
        response = web_client.get("/monitor-status")
        html = response.text
        lines = html.split("\n")
        for line in lines:
            if "启动后将自动抓取" in line:
                assert "text-gray-400" in line
                break
        else:
            pytest.fail("Monitor description text not found")

    def test_settings_weight_hint_contrast(self, web_client):
        """Settings weight hint uses text-gray-400."""
        response = web_client.get("/settings")
        html = response.text
        lines = html.split("\n")
        for line in lines:
            if "权重调整功能即将推出" in line:
                assert "text-gray-400" in line
                break
        else:
            pytest.fail("Settings weight hint not found")


class TestSearchFilterInDB:
    """The database query function supports search filter."""

    def test_build_filter_clause_with_search(self):
        """_build_filter_clause includes search LIKE condition."""
        from src.storage.db import _build_filter_clause

        sql, params = _build_filter_clause({"search": "hello"})
        assert "title LIKE" in sql
        assert "summary LIKE" in sql
        assert "%hello%" in params
