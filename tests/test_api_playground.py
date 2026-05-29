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
