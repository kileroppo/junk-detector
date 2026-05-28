"""Tests for FEAT-001: Core experience improvements (Rounds 1-2).

Verify:
- Dashboard shows empty state when stats.total == 0
- Score form has value proposition text
- Nav links have aria-label attributes
- Score form submit button container has sticky class for mobile
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


class TestDashboardEmptyState:
    """Verify dashboard shows helpful empty state when no scores exist."""

    @patch("src.web.routes.pages.get_history")
    def test_empty_dashboard_shows_empty_state(self, mock_history, web_client):
        """When stats.total == 0, dashboard shows empty state UI."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert "dashboard-empty-state" in html
        assert "还没有评分记录" in html

    @patch("src.web.routes.pages.get_history")
    def test_empty_dashboard_has_cta_button(self, mock_history, web_client):
        """Empty state includes a CTA link to /score-form."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert 'href="/score-form"' in html
        assert "开始评分" in html

    @patch("src.web.routes.pages.get_history")
    def test_empty_dashboard_has_try_sample_button(self, mock_history, web_client):
        """Empty state includes a 'Try sample' button with hx-post."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert 'hx-post="/score-submit"' in html
        assert "试试示例" in html

    @patch("src.web.routes.pages.get_history")
    def test_non_empty_dashboard_shows_stats(self, mock_history, web_client):
        """When stats.total > 0, normal dashboard content is shown."""
        mock_history.return_value = [
            {"overall_score": 80.0},
            {"overall_score": 50.0},
        ]
        response = web_client.get("/dashboard")
        html = response.text

        assert "总评分数" in html
        assert "dashboard-empty-state" not in html


class TestScoreFormValueProposition:
    """Verify score form includes value proposition text."""

    def test_score_form_has_value_proposition(self, web_client):
        """Score form renders value proposition hero text."""
        response = web_client.get("/score-form")
        html = response.text

        assert "value-proposition" in html
        assert "粘贴文本或输入网址" in html
        assert "9个维度" in html

    def test_score_form_has_sticky_submit_button(self, web_client):
        """Score form submit button is wrapped in sticky container for mobile."""
        response = web_client.get("/score-form")
        html = response.text

        assert "sticky bottom-4" in html
        assert "sm:static" in html

    def test_score_form_inputs_have_min_height(self, web_client):
        """Score form inputs have min-h-[44px] for mobile touch targets."""
        response = web_client.get("/score-form")
        html = response.text

        assert "min-h-[44px]" in html


class TestNavAriaLabels:
    """Verify navigation links have aria-label attributes."""

    def test_nav_has_aria_labels(self, web_client):
        """All desktop nav links include aria-label attributes."""
        response = web_client.get("/score-form")
        html = response.text

        assert 'aria-label="仪表盘 - 查看评分统计和趋势"' in html
        assert 'aria-label="评分 - 输入内容进行AI质量分析"' in html
        assert 'aria-label="历史记录 - 查看过去的评分结果"' in html
        assert 'aria-label="监控 - Thunder信源监控管理"' in html
        assert 'aria-label="对比 - 多篇内容质量对比分析"' in html
        assert 'aria-label="设置 - 配置API密钥和偏好"' in html

    @patch("src.web.routes.pages.get_history")
    def test_dashboard_nav_has_aria_labels(self, mock_history, web_client):
        """Dashboard page also renders nav with aria-labels."""
        mock_history.return_value = []
        response = web_client.get("/dashboard")
        html = response.text

        assert 'aria-label="仪表盘 - 查看评分统计和趋势"' in html


class TestHistoryMobileCards:
    """Verify history mobile card improvements."""

    @patch("src.web.routes.pages.get_history")
    def test_history_cards_have_min_height(self, mock_history, web_client):
        """History mobile cards have min-h-[44px] class."""
        mock_history.return_value = [
            {
                "id": 1,
                "title": "Test Article",
                "overall_score": 75.0,
                "scored_at": "2025-01-15T10:00:00",
                "labels": [],
                "summary": "Test summary",
                "source_url": None,
                "content_hash": "abc123",
            },
        ]
        response = web_client.get("/history-page")
        html = response.text

        assert "min-h-[44px]" in html

    @patch("src.web.routes.pages.get_history")
    def test_history_first_card_has_swipe_hint(self, mock_history, web_client):
        """First history card has swipe hint text."""
        mock_history.return_value = [
            {
                "id": 1,
                "title": "Test Article",
                "overall_score": 75.0,
                "scored_at": "2025-01-15T10:00:00",
                "labels": [],
                "summary": "Test summary",
                "source_url": None,
                "content_hash": "abc123",
            },
        ]
        response = web_client.get("/history-page")
        html = response.text

        assert "滑动操作" in html
        assert "swipe-hint" in html
