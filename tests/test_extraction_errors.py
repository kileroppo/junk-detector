"""Tests for user-facing URL fetch error classification."""

from __future__ import annotations

from src.web.extraction_errors import classify_fetch_error


class TestClassifyFetchError:
    def test_timeout(self):
        info = classify_fetch_error(
            TimeoutError("Request timed out after 30s: https://slow.example/a"),
            url="https://slow.example/a",
        )
        assert info.code == "timeout"
        assert info.title == "网页打开超时"
        assert len(info.hints) >= 1

    def test_not_found(self):
        info = classify_fetch_error(
            ValueError("URL returned 404 Not Found: https://x.test/missing"),
            url="https://x.test/missing",
        )
        assert info.code == "not_found"
        assert "404" in info.reason or "不存在" in info.reason

    def test_auth_required(self):
        info = classify_fetch_error(
            ValueError(
                "该网站拒绝了访问（HTTP 403）。请先登录：junk-detector auth login --platform zhihu"
            ),
            url="https://zhihu.com/p/1",
        )
        assert info.code == "auth_required"
        assert info.level == "warning"
        assert any("Cookie" in h for h in info.hints)

    def test_empty_content(self):
        info = classify_fetch_error(
            ValueError("Could not extract any text content from: https://x.test"),
            url="https://x.test",
        )
        assert info.code == "empty_content"
        assert "正文" in info.reason

    def test_network(self):
        info = classify_fetch_error(
            ValueError("Failed to fetch URL: https://down.test — connection refused"),
            url="https://down.test",
        )
        assert info.code == "network"
        assert info.title == "无法连接该网站"
