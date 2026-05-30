"""Tests for the /playground endpoint."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def test_playground_returns_html():
    response = client.get("/playground")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "鉴真" in response.text or "playground" in response.text.lower()


def test_playground_has_input_and_button():
    response = client.get("/playground")
    assert "textarea" in response.text or "input" in response.text
    assert "检测" in response.text or "Score" in response.text


def test_playground_uses_post_method():
    """Playground page should use POST method for /demo requests."""
    response = client.get("/playground")
    assert response.status_code == 200
    # Check that the fetch uses POST, not GET with query params
    assert "method" in response.text
    assert "POST" in response.text
    assert "application/json" in response.text


def test_post_demo_with_text():
    """POST /demo should accept JSON body with text field."""
    response = client.post("/demo", json={"text": "日入过万 加微信领取"})
    assert response.status_code == 200
    data = response.json()
    assert "verdict" in data
    assert "overall_score" in data
    assert data["is_custom_text"] is True


def test_post_demo_without_text():
    """POST /demo without text should use default sample."""
    response = client.post("/demo", json={})
    assert response.status_code == 200
    data = response.json()
    assert "verdict" in data
    assert data["is_custom_text"] is False


def test_post_demo_null_text():
    """POST /demo with null text should use default sample."""
    response = client.post("/demo", json={"text": None})
    assert response.status_code == 200
    data = response.json()
    assert data["is_custom_text"] is False
