"""Tests for the source reputation system (src.core.source_reputation).

Covers domain normalization, blacklist/whitelist loading, auto-blacklist
logic, and score adjustments.
"""

from __future__ import annotations

from unittest.mock import patch

from src.core.source_reputation import (
    _normalize_domain,
    check_auto_blacklist,
    get_source_adjustment,
    is_blacklisted,
    is_whitelisted,
    load_source_lists,
)


class TestNormalizeDomain:
    """Tests for _normalize_domain helper."""

    def test_lowercases(self):
        assert _normalize_domain("Example.COM") == "example.com"

    def test_strips_www(self):
        assert _normalize_domain("www.example.com") == "example.com"

    def test_strips_www_and_lowercases(self):
        assert _normalize_domain("WWW.Example.Com") == "example.com"

    def test_empty_string(self):
        assert _normalize_domain("") == ""

    def test_strips_whitespace(self):
        assert _normalize_domain("  example.com  ") == "example.com"

    def test_no_www_prefix(self):
        assert _normalize_domain("news.example.com") == "news.example.com"


class TestLoadSourceLists:
    """Tests for load_source_lists with a temp config file."""

    def test_loads_blacklist_and_whitelist(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "sources:\n"
            "  blacklist:\n"
            "    - spam-domain.com\n"
            "    - Fake-News.CN\n"
            "  whitelist:\n"
            "    - trusted-source.com\n"
            "    - WWW.Reuters.com\n"
        )
        blacklist, whitelist = load_source_lists(str(config_file))
        assert blacklist == {"spam-domain.com", "fake-news.cn"}
        assert whitelist == {"trusted-source.com", "reuters.com"}

    def test_empty_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sources:\n  blacklist: []\n  whitelist: []\n")
        blacklist, whitelist = load_source_lists(str(config_file))
        assert blacklist == set()
        assert whitelist == set()

    def test_missing_sources_section(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("other_key: value\n")
        blacklist, whitelist = load_source_lists(str(config_file))
        assert blacklist == set()
        assert whitelist == set()

    def test_nonexistent_config_path(self, tmp_path):
        blacklist, whitelist = load_source_lists(str(tmp_path / "nope.yaml"))
        assert blacklist == set()
        assert whitelist == set()


class TestIsBlacklisted:
    """Tests for is_blacklisted."""

    def test_blacklisted_domain(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sources:\n  blacklist:\n    - spam.com\n  whitelist: []\n")
        assert is_blacklisted("spam.com", str(config_file)) is True

    def test_non_blacklisted_domain(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sources:\n  blacklist:\n    - spam.com\n  whitelist: []\n")
        assert is_blacklisted("good.com", str(config_file)) is False

    def test_www_prefix_normalized(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sources:\n  blacklist:\n    - spam.com\n  whitelist: []\n")
        assert is_blacklisted("www.spam.com", str(config_file)) is True


class TestIsWhitelisted:
    """Tests for is_whitelisted."""

    def test_whitelisted_domain(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sources:\n  blacklist: []\n  whitelist:\n    - trusted.org\n")
        assert is_whitelisted("trusted.org", str(config_file)) is True

    def test_non_whitelisted_domain(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sources:\n  blacklist: []\n  whitelist:\n    - trusted.org\n")
        assert is_whitelisted("unknown.org", str(config_file)) is False


class TestCheckAutoBlacklist:
    """Tests for check_auto_blacklist with mocked query_by_domain."""

    def _make_config(self, tmp_path, enabled=True, min_articles=5, max_avg_score=30):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "sources:\n"
            "  blacklist: []\n"
            "  whitelist: []\n"
            "  auto_blacklist:\n"
            f"    enabled: {str(enabled).lower()}\n"
            f"    min_articles: {min_articles}\n"
            f"    max_avg_score: {max_avg_score}\n"
        )
        return str(config_file)

    @patch("src.storage.db.query_by_domain")
    def test_returns_true_when_qualifies(self, mock_query, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path)
        mock_query.return_value = [20.0, 25.0, 15.0, 30.0, 10.0]  # avg=20, count=5
        result = check_auto_blacklist("bad-site.com", db_path=tmp_db_path, config_path=config)
        assert result is True
        mock_query.assert_called_once_with("bad-site.com", db_path=tmp_db_path)

    @patch("src.storage.db.query_by_domain")
    def test_returns_false_when_disabled(self, mock_query, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path, enabled=False)
        mock_query.return_value = [10.0, 10.0, 10.0, 10.0, 10.0]
        result = check_auto_blacklist("bad-site.com", db_path=tmp_db_path, config_path=config)
        assert result is False
        mock_query.assert_not_called()

    @patch("src.storage.db.query_by_domain")
    def test_returns_false_not_enough_articles(self, mock_query, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path, min_articles=5)
        mock_query.return_value = [20.0, 25.0, 15.0]  # only 3 articles
        result = check_auto_blacklist("new-site.com", db_path=tmp_db_path, config_path=config)
        assert result is False

    @patch("src.storage.db.query_by_domain")
    def test_returns_false_when_avg_too_high(self, mock_query, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path, max_avg_score=30)
        mock_query.return_value = [50.0, 60.0, 70.0, 80.0, 90.0]  # avg=70
        result = check_auto_blacklist("decent-site.com", db_path=tmp_db_path, config_path=config)
        assert result is False


class TestGetSourceAdjustment:
    """Tests for get_source_adjustment."""

    def _make_config(
        self, tmp_path, blacklist=None, whitelist=None, penalty=30, boost=5, auto_enabled=False
    ):
        blacklist = blacklist or []
        whitelist = whitelist or []
        bl_str = ", ".join(f'"{d}"' for d in blacklist)
        wl_str = ", ".join(f'"{d}"' for d in whitelist)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "sources:\n"
            f"  blacklist: [{bl_str}]\n"
            f"  whitelist: [{wl_str}]\n"
            f"  blacklist_penalty: {penalty}\n"
            f"  whitelist_boost: {boost}\n"
            "  auto_blacklist:\n"
            f"    enabled: {str(auto_enabled).lower()}\n"
            "    min_articles: 5\n"
            "    max_avg_score: 30\n"
        )
        return str(config_file)

    def test_blacklisted_domain(self, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path, blacklist=["spam.com"], penalty=30)
        adj, reason = get_source_adjustment("spam.com", config_path=config, db_path=tmp_db_path)
        assert adj == -30
        assert reason == "来源已列入黑名单"

    def test_whitelisted_domain(self, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path, whitelist=["trusted.com"], boost=5)
        adj, reason = get_source_adjustment("trusted.com", config_path=config, db_path=tmp_db_path)
        assert adj == 5
        assert reason == "可信来源"

    def test_normal_domain(self, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path)
        adj, reason = get_source_adjustment("normal.com", config_path=config, db_path=tmp_db_path)
        assert adj == 0
        assert reason == ""

    def test_none_domain(self, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path)
        adj, reason = get_source_adjustment(None, config_path=config, db_path=tmp_db_path)
        assert adj == 0
        assert reason == ""

    @patch("src.storage.db.query_by_domain")
    def test_auto_blacklisted_domain(self, mock_query, tmp_path, tmp_db_path):
        config = self._make_config(tmp_path, auto_enabled=True)
        mock_query.return_value = [10.0, 15.0, 20.0, 25.0, 10.0]  # avg=16, count=5
        adj, reason = get_source_adjustment(
            "lowquality.com", config_path=config, db_path=tmp_db_path
        )
        assert adj == -20
        assert reason == "来源历史评分极低"
