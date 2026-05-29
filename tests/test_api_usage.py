"""Tests for the /usage endpoint."""

import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def test_usage_returns_json():
    response = client.get("/usage")
    assert response.status_code == 200
    data = response.json()
    assert "used" in data
    assert "limit" in data
    assert "resets_at" in data
    assert "tier" in data


def test_usage_limit_is_30():
    response = client.get("/usage")
    data = response.json()
    assert data["limit"] == 30
    assert data["tier"] == "free"


def test_usage_resets_at_is_iso_format():
    response = client.get("/usage")
    data = response.json()
    from datetime import datetime

    # Should be valid ISO format
    datetime.fromisoformat(data["resets_at"])
