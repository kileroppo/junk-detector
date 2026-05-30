"""Comprehensive tests for the crawler_auth module."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.crawler_auth import AuthenticatedClient, CookieStore, SignerHook
from src.crawler_auth.base import PlatformAuth as PlatformAuthProtocol
from src.crawler_auth.platforms import (
    PLATFORMS,
    BilibiliAuth,
    WechatAuth,
    WeiboAuth,
    XiaohongshuAuth,
    ZhihuAuth,
)

# =============================================================================
# TestCookieStore
# =============================================================================


class TestCookieStore:
    """Tests for CookieStore persistence and TTL logic."""

    def test_save_and_load(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        cookies = {"session_id": "abc123", "token": "xyz789"}
        store.save("zhihu", cookies)

        loaded = store.load("zhihu")
        assert loaded == cookies

    def test_load_nonexistent(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        assert store.load("nonexistent") is None

    def test_expire_cookies(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        cookies = {"session_id": "abc"}
        store.save("weibo", cookies, ttl_hours=0)  # Immediate expiry

        # Wait a tiny bit to ensure expiry
        time.sleep(0.01)
        assert store.load("weibo") is None
        assert store.is_expired("weibo") is True

    def test_not_expired(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        cookies = {"session_id": "abc"}
        store.save("zhihu", cookies, ttl_hours=168)

        assert store.is_expired("zhihu") is False
        assert store.load("zhihu") == cookies

    def test_clear(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        store.save("bilibili", {"key": "val"})
        store.clear("bilibili")
        assert store.load("bilibili") is None

    def test_list_platforms(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"a": "1"})
        store.save("weibo", {"b": "2"})
        store.save("bilibili", {"c": "3"})

        platforms = store.list_platforms()
        assert set(platforms) == {"zhihu", "weibo", "bilibili"}

    def test_clear_nonexistent_no_error(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        store.clear("nope")  # Should not raise

    def test_is_expired_missing_platform(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        assert store.is_expired("missing") is True

    def test_corrupted_json(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        # Write corrupted data
        (tmp_path / "broken.json").write_text("not json{{")
        assert store.load("broken") is None
        assert store.is_expired("broken") is True

    def test_path_traversal_rejected(self, tmp_path: Path):
        """Platform names with path traversal characters should raise ValueError."""
        store = CookieStore(store_dir=tmp_path)
        with pytest.raises(ValueError, match="Invalid platform name"):
            store.save("../../etc/shadow", {"key": "val"})
        with pytest.raises(ValueError, match="Invalid platform name"):
            store.load("../secret")
        with pytest.raises(ValueError, match="Invalid platform name"):
            store.save("foo/bar", {"key": "val"})
        with pytest.raises(ValueError, match="Invalid platform name"):
            store.save("foo\\bar", {"key": "val"})
        with pytest.raises(ValueError, match="Invalid platform name"):
            store.save("", {"key": "val"})

    def test_file_permissions(self, tmp_path: Path):
        """Cookie files should be written with restrictive permissions (0o600)."""
        import os
        import stat

        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"session": "abc"})
        path = tmp_path / "zhihu.json"
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o600

    def test_load_unchecked_ignores_expiry(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"old": "1"}, ttl_hours=0)
        time.sleep(0.01)
        assert store.load("zhihu") is None
        assert store.load_unchecked("zhihu") == {"old": "1"}

    def test_update_merge(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"a": "1", "b": "2"})
        merged = store.update("zhihu", {"b": "updated", "c": "3"}, merge=True)
        assert merged == {"a": "1", "b": "updated", "c": "3"}
        assert store.load("zhihu") == merged

    def test_update_replace(self, tmp_path: Path):
        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"a": "1"})
        merged = store.update("zhihu", {"b": "2"}, merge=False)
        assert merged == {"b": "2"}


# =============================================================================
# TestCookieUtils
# =============================================================================


class TestCookieUtils:
    def test_parse_semicolon_string(self):
        from src.crawler_auth.cookie_utils import parse_cookie_string

        raw = "z_c0=abc; __zse_ck=def"
        assert parse_cookie_string(raw) == {"z_c0": "abc", "__zse_ck": "def"}

    def test_parse_cookie_header_prefix(self):
        from src.crawler_auth.cookie_utils import parse_cookie_string

        raw = "Cookie: z_c0=abc; __zse_ck=def"
        assert parse_cookie_string(raw) == {"z_c0": "abc", "__zse_ck": "def"}

    def test_parse_json(self):
        from src.crawler_auth.cookie_utils import parse_cookie_string

        raw = '{"z_c0": "abc", "__zse_ck": "def"}'
        assert parse_cookie_string(raw) == {"z_c0": "abc", "__zse_ck": "def"}

    def test_parse_empty_raises(self):
        from src.crawler_auth.cookie_utils import parse_cookie_string

        with pytest.raises(ValueError, match="Empty"):
            parse_cookie_string("   ")


# =============================================================================
# TestCookieManager
# =============================================================================


class TestCookieManager:
    def test_list_all_platform_statuses(self, tmp_path: Path):
        from src.crawler_auth import CookieStore, list_all_platform_statuses

        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"z_c0": "abc"})
        statuses = list_all_platform_statuses(store)
        ids = {s["id"] for s in statuses}
        assert "zhihu" in ids
        assert "weibo" in ids
        zhihu = next(s for s in statuses if s["id"] == "zhihu")
        assert zhihu["status"] == "active"
        assert zhihu["cookie_count"] == 1

    def test_import_cookies_merge(self, tmp_path: Path):
        from src.crawler_auth import CookieStore, import_cookies

        store = CookieStore(store_dir=tmp_path)
        store.save("weibo", {"SUB": "old"})
        result = import_cookies("weibo", "SUB=new; _T_WM=1", store=store)
        assert result["total_count"] == 2
        assert "SUB" in result["imported_keys"]

    def test_clear_platform_cookies(self, tmp_path: Path):
        from src.crawler_auth import CookieStore, clear_platform_cookies

        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"z_c0": "abc"})
        result = clear_platform_cookies("zhihu", store=store)
        assert result["platform"]["status"] == "missing"


# =============================================================================
# TestPlatformDetection
# =============================================================================


class TestPlatformDetection:
    """Tests for AuthenticatedClient.detect_platform()."""

    def setup_method(self):
        self.client = AuthenticatedClient()

    def test_zhihu_urls(self):
        assert self.client.detect_platform("https://www.zhihu.com/question/123") == "zhihu"
        assert self.client.detect_platform("https://zhihu.com/hot") == "zhihu"
        assert self.client.detect_platform("https://zhuanlan.zhihu.com/p/456") == "zhihu"

    def test_weibo_urls(self):
        assert self.client.detect_platform("https://weibo.com/u/123") == "weibo"
        assert self.client.detect_platform("https://www.weibo.com/hot") == "weibo"
        assert self.client.detect_platform("https://s.weibo.com/weibo?q=test") == "weibo"
        assert self.client.detect_platform("https://m.weibo.cn/detail/123") == "weibo"

    def test_xiaohongshu_urls(self):
        assert (
            self.client.detect_platform("https://www.xiaohongshu.com/explore/abc")
            == "xiaohongshu"
        )
        assert self.client.detect_platform("https://xhslink.com/abc") == "xiaohongshu"

    def test_wechat_urls(self):
        assert (
            self.client.detect_platform("https://weixin.sogou.com/weixin?query=test")
            == "wechat"
        )
        assert self.client.detect_platform("https://mp.weixin.qq.com/s/abc") == "wechat"

    def test_bilibili_urls(self):
        assert self.client.detect_platform("https://www.bilibili.com/video/BV123") == "bilibili"
        assert self.client.detect_platform("https://b23.tv/abc") == "bilibili"
        assert (
            self.client.detect_platform("https://api.bilibili.com/x/web-interface/nav")
            == "bilibili"
        )

    def test_unknown_urls(self):
        assert self.client.detect_platform("https://www.google.com") is None
        assert self.client.detect_platform("https://example.com") is None
        assert self.client.detect_platform("https://github.com/repo") is None


# =============================================================================
# TestPlatformHeaders
# =============================================================================


class TestPlatformHeaders:
    """Tests that each platform generates correct headers."""

    def test_zhihu_headers(self):
        auth = ZhihuAuth()
        cookies = {"z_c0": "token_value", "_xsrf": "csrf_val"}
        headers = auth.get_headers(cookies, "https://www.zhihu.com/api/v4/questions")

        assert "Cookie" in headers
        assert "z_c0=token_value" in headers["Cookie"]
        assert "User-Agent" in headers

    def test_weibo_headers(self):
        auth = WeiboAuth()
        cookies = {"SUB": "sub_val", "SUBP": "subp_val"}
        headers = auth.get_headers(cookies)

        assert "Cookie" in headers
        assert "SUB=sub_val" in headers["Cookie"]
        assert "iPhone" in headers["User-Agent"]
        assert headers["Referer"] == "https://m.weibo.cn/"

    def test_weibo_h5_config(self):
        auth = WeiboAuth()
        assert "mweibo" in auth.login_url
        assert "weibo.cn" in auth.cookie_domains

    def test_xiaohongshu_headers(self):
        auth = XiaohongshuAuth()
        cookies = {"a1": "val1", "webId": "id123"}
        headers = auth.get_headers(cookies, "https://www.xiaohongshu.com/api/sns/v1")

        assert "Cookie" in headers
        assert "Origin" in headers
        assert headers["Origin"] == "https://www.xiaohongshu.com"

    def test_wechat_headers(self):
        auth = WechatAuth()
        cookies = {"SNUID": "snuid_val", "ABTEST": "ab_val"}
        headers = auth.get_headers(cookies)

        assert "Cookie" in headers
        assert "SNUID=snuid_val" in headers["Cookie"]

    def test_bilibili_headers(self):
        auth = BilibiliAuth()
        cookies = {"SESSDATA": "sess_val", "bili_jct": "csrf_token_123"}
        headers = auth.get_headers(cookies, "https://api.bilibili.com/x/web-interface/nav")

        assert "Cookie" in headers
        assert "x-csrf-token" in headers
        assert headers["x-csrf-token"] == "csrf_token_123"
        assert "Referer" in headers

    def test_bilibili_headers_no_csrf(self):
        auth = BilibiliAuth()
        cookies = {"SESSDATA": "sess_val"}
        headers = auth.get_headers(cookies)

        assert "Cookie" in headers
        assert "x-csrf-token" not in headers


# =============================================================================
# TestBrowserLogin
# =============================================================================


class TestBrowserLogin:
    """Tests for browser_login with mocked Playwright."""

    async def test_browser_login_success(self):
        """Test browser login flow with mocked playwright."""
        mock_cookie = [
            {"name": "session", "value": "abc123", "domain": ".zhihu.com"},
            {"name": "token", "value": "xyz", "domain": ".zhihu.com"},
            {"name": "other", "value": "val", "domain": ".google.com"},
        ]

        mock_page = AsyncMock()
        mock_page.url = "https://www.zhihu.com/hot"  # Already navigated away
        mock_page.goto = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=MagicMock())

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.cookies = AsyncMock(return_value=mock_cookie)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_pw_context.__aexit__ = AsyncMock(return_value=False)

        mock_async_pw = MagicMock(return_value=mock_pw_context)

        with patch(
            "playwright.async_api.async_playwright",
            mock_async_pw,
        ):
            from src.crawler_auth.browser_login import browser_login

            result = await browser_login(
                login_url="https://www.zhihu.com/signin",
                cookie_domains=["zhihu.com"],
                headless=True,
                wait_for_login_indicator=".AppHeader-profileAvatar",
            )

        assert "session" in result
        assert result["session"] == "abc123"
        assert "token" in result
        # google.com cookie should be excluded
        assert "other" not in result

    async def test_browser_login_import_error(self):
        """Test graceful handling when playwright is not installed."""
        import sys

        # Remove playwright from sys.modules temporarily
        orig_modules = {}
        for key in list(sys.modules.keys()):
            if "playwright" in key:
                orig_modules[key] = sys.modules.pop(key)

        try:
            with patch.dict(
                "sys.modules",
                {"playwright": None, "playwright.async_api": None},
            ):
                from src.crawler_auth.browser_login import browser_login as bl_fn

                with pytest.raises(ImportError, match="playwright"):
                    await bl_fn(
                        login_url="https://test.com",
                        cookie_domains=["test.com"],
                    )
        finally:
            # Restore modules
            sys.modules.update(orig_modules)

    async def test_browser_login_domain_suffix_matching(self):
        """Test that cookie domain matching uses suffix match, not substring.

        Cookies from 'not-zhihu.com' should NOT be included when
        cookie_domains is ['zhihu.com'].
        """
        mock_cookie = [
            {"name": "session", "value": "abc123", "domain": ".zhihu.com"},
            {"name": "sub_session", "value": "sub", "domain": ".sub.zhihu.com"},
            {"name": "bad", "value": "evil", "domain": ".not-zhihu.com"},
            {"name": "other", "value": "val", "domain": ".google.com"},
        ]

        mock_page = AsyncMock()
        mock_page.url = "https://www.zhihu.com/hot"  # Already navigated away
        mock_page.goto = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=MagicMock())

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.cookies = AsyncMock(return_value=mock_cookie)

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_pw_context = AsyncMock()
        mock_pw_context.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_pw_context.__aexit__ = AsyncMock(return_value=False)

        mock_async_pw = MagicMock(return_value=mock_pw_context)

        with patch(
            "playwright.async_api.async_playwright",
            mock_async_pw,
        ):
            from src.crawler_auth.browser_login import browser_login

            result = await browser_login(
                login_url="https://www.zhihu.com/signin",
                cookie_domains=["zhihu.com"],
                headless=True,
                wait_for_login_indicator=".AppHeader-profileAvatar",
            )

        # zhihu.com and sub.zhihu.com should be included
        assert "session" in result
        assert result["session"] == "abc123"
        assert "sub_session" in result
        assert result["sub_session"] == "sub"
        # not-zhihu.com should be EXCLUDED (suffix match, not substring)
        assert "bad" not in result
        # google.com should be excluded
        assert "other" not in result


# =============================================================================
# TestAuthenticatedClient
# =============================================================================


class TestAuthenticatedClient:
    """Tests for AuthenticatedClient fetch pipeline."""

    def test_auto_discovers_platforms(self):
        client = AuthenticatedClient()
        # With lazy instantiation, platforms are created on demand
        assert client._get_platform("zhihu") is not None
        assert client._get_platform("weibo") is not None
        assert client._get_platform("xiaohongshu") is not None
        assert client._get_platform("wechat") is not None
        assert client._get_platform("bilibili") is not None

    def test_custom_platforms(self):
        mock_platform = MagicMock()
        mock_platform.platform_name = "custom"
        client = AuthenticatedClient(platforms={"custom": mock_platform})
        assert "custom" in client._platforms
        assert "zhihu" not in client._platforms

    async def test_fetch_with_platform(self, tmp_path: Path):
        """Test fetch with mocked HTTP response."""
        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"z_c0": "test_token"})

        client = AuthenticatedClient(cookie_store=store)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>content</html>"

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            resp = await client.fetch("https://www.zhihu.com/hot")
            assert resp.status_code == 200

    async def test_fetch_unknown_platform(self):
        """Test fetch for unknown platform uses plain request."""
        client = AuthenticatedClient()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            resp = await client.fetch("https://example.com/page")
            assert resp.status_code == 200

    async def test_ensure_login_with_valid_cookies(self, tmp_path: Path):
        """Test that ensure_login skips login if cookies are valid."""
        store = CookieStore(store_dir=tmp_path)
        store.save("zhihu", {"z_c0": "valid_token"})

        mock_platform = AsyncMock()
        mock_platform.platform_name = "zhihu"
        mock_platform.validate_cookies = AsyncMock(return_value=True)
        mock_platform.login = AsyncMock()

        client = AuthenticatedClient(
            cookie_store=store, platforms={"zhihu": mock_platform}
        )
        await client.ensure_login("zhihu")

        # login should NOT have been called since cookies are valid
        mock_platform.login.assert_not_called()

    async def test_ensure_login_with_expired_cookies(self, tmp_path: Path):
        """Test that ensure_login triggers login if cookies expired."""
        store = CookieStore(store_dir=tmp_path)
        # Save with 0 TTL so they expire immediately
        store.save("zhihu", {"z_c0": "old"}, ttl_hours=0)
        time.sleep(0.01)

        mock_platform = AsyncMock()
        mock_platform.platform_name = "zhihu"
        mock_platform.login = AsyncMock(return_value={"z_c0": "new_token"})

        client = AuthenticatedClient(
            cookie_store=store, platforms={"zhihu": mock_platform}
        )
        await client.ensure_login("zhihu")

        mock_platform.login.assert_called_once_with(headless=False)
        # Cookies should be saved
        assert store.load("zhihu") == {"z_c0": "new_token"}

    async def test_ensure_login_unknown_platform(self):
        """Test ensure_login raises for unknown platform."""
        client = AuthenticatedClient(platforms={})
        with pytest.raises(ValueError, match="Unknown platform"):
            await client.ensure_login("nonexistent")

    def test_get_client_returns_async_client(self, tmp_path: Path):
        """Test get_client returns configured httpx.AsyncClient."""
        store = CookieStore(store_dir=tmp_path)
        store.save("bilibili", {"SESSDATA": "val", "bili_jct": "csrf"})

        client = AuthenticatedClient(cookie_store=store)
        async_client = client.get_client("bilibili")
        assert isinstance(async_client, httpx.AsyncClient)


# =============================================================================
# TestSignerHook
# =============================================================================


class TestSignerHook:
    """Tests for the SignerHook protocol and integration with platforms."""

    def test_signer_protocol_check(self):
        """Verify SignerHook is a runtime checkable protocol."""

        class MySigner:
            def sign(self, url: str, cookies: dict[str, str]) -> dict[str, str]:
                return {"x-zse-96": f"2.0_signed_{url}"}

        signer = MySigner()
        assert isinstance(signer, SignerHook)

    def test_zhihu_with_signer_hook(self):
        """Test that ZhihuAuth invokes signer_hook in get_headers."""

        class ZhihuSigner:
            def sign(self, url: str, cookies: dict[str, str]) -> dict[str, str]:
                return {"x-zse-96": "2.0_ABCDEF", "x-zst-81": "sig_value"}

        signer = ZhihuSigner()
        auth = ZhihuAuth(signer_hook=signer)
        cookies = {"z_c0": "token"}
        headers = auth.get_headers(cookies, "https://www.zhihu.com/api/v4/questions")

        assert headers["x-zse-96"] == "2.0_ABCDEF"
        assert headers["x-zst-81"] == "sig_value"
        assert "Cookie" in headers

    def test_xiaohongshu_with_signer_hook(self):
        """Test that XiaohongshuAuth invokes signer_hook in get_headers."""

        class XhsSigner:
            def sign(self, url: str, cookies: dict[str, str]) -> dict[str, str]:
                return {"x-s": "signed_val", "x-t": "1234567890"}

        signer = XhsSigner()
        auth = XiaohongshuAuth(signer_hook=signer)
        cookies = {"a1": "val"}
        headers = auth.get_headers(cookies, "https://www.xiaohongshu.com/api/sns/v1")

        assert headers["x-s"] == "signed_val"
        assert headers["x-t"] == "1234567890"

    def test_zhihu_without_signer_hook(self):
        """Test ZhihuAuth works without signer_hook."""
        auth = ZhihuAuth()
        cookies = {"z_c0": "token"}
        headers = auth.get_headers(cookies, "https://www.zhihu.com/api/v4")

        assert "x-zse-96" not in headers
        assert "Cookie" in headers

    def test_xiaohongshu_without_signer_hook(self):
        """Test XiaohongshuAuth works without signer_hook."""
        auth = XiaohongshuAuth()
        cookies = {"a1": "val"}
        headers = auth.get_headers(cookies, "https://www.xiaohongshu.com/api/sns/v1")

        assert "x-s" not in headers
        assert "Cookie" in headers

    def test_non_signer_does_not_match_protocol(self):
        """Objects without sign() method should not match SignerHook."""

        class NotASigner:
            def compute(self, url: str) -> str:
                return "nope"

        assert not isinstance(NotASigner(), SignerHook)


# =============================================================================
# TestProtocolCompliance
# =============================================================================


class TestProtocolCompliance:
    """Verify all platform classes implement the PlatformAuth protocol."""

    def test_zhihu_is_platform_auth(self):
        assert isinstance(ZhihuAuth(), PlatformAuthProtocol)

    def test_weibo_is_platform_auth(self):
        assert isinstance(WeiboAuth(), PlatformAuthProtocol)

    def test_xiaohongshu_is_platform_auth(self):
        assert isinstance(XiaohongshuAuth(), PlatformAuthProtocol)

    def test_wechat_is_platform_auth(self):
        assert isinstance(WechatAuth(), PlatformAuthProtocol)

    def test_bilibili_is_platform_auth(self):
        assert isinstance(BilibiliAuth(), PlatformAuthProtocol)

    def test_platforms_registry_complete(self):
        assert len(PLATFORMS) == 5
        assert set(PLATFORMS.keys()) == {
            "zhihu", "weibo", "xiaohongshu", "wechat", "bilibili"
        }


# =============================================================================
# TestCLIAuth
# =============================================================================


class TestCLIAuth:
    """Tests for CLI auth subcommand integration."""

    def test_auth_commands_registered(self):
        """Verify auth subcommand group is registered with login/status/logout."""
        from typer.testing import CliRunner

        from src.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output
        assert "status" in result.output
        assert "logout" in result.output
        assert "import" in result.output

    def test_auth_login_unknown_platform(self):
        """Login with an unknown platform should fail."""
        from typer.testing import CliRunner

        from src.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["auth", "login", "--platform", "fakebook"])
        assert result.exit_code == 1
        assert "Unknown platform" in result.output

    def test_auth_login_success_mocked(self, tmp_path: Path):
        """Test auth login with mocked browser login."""
        from typer.testing import CliRunner

        from src.cli.main import app

        mock_cookies = {"z_c0": "token_123", "_xsrf": "csrf_val"}

        with patch(
            "src.crawler_auth.platforms.zhihu.ZhihuAuth.login",
            new_callable=AsyncMock,
            return_value=mock_cookies,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.__init__",
            return_value=None,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.save",
        ) as mock_save:
            runner = CliRunner()
            result = runner.invoke(app, ["auth", "login", "--platform", "zhihu", "--headless"])
            assert result.exit_code == 0
            assert "Login successful" in result.output
            mock_save.assert_called_once()

    def test_auth_status(self, tmp_path: Path):
        """Test auth status shows platform info."""
        from typer.testing import CliRunner

        from src.cli.main import app

        with patch(
            "src.crawler_auth.cookie_store.CookieStore.__init__",
            return_value=None,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.load",
            return_value={"z_c0": "token"},
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.is_expired",
            return_value=False,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.list_platforms",
            return_value=["zhihu"],
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["auth", "status"])
            assert result.exit_code == 0
            assert "zhihu" in result.output

    def test_auth_logout_specific_platform(self, tmp_path: Path):
        """Test logout clears specific platform cookies."""
        from typer.testing import CliRunner

        from src.cli.main import app

        with patch(
            "src.crawler_auth.cookie_store.CookieStore.__init__",
            return_value=None,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.clear",
        ) as mock_clear:
            runner = CliRunner()
            result = runner.invoke(app, ["auth", "logout", "--platform", "zhihu"])
            assert result.exit_code == 0
            assert "Cleared cookies" in result.output
            mock_clear.assert_called_once_with("zhihu")

    def test_auth_logout_all(self, tmp_path: Path):
        """Test logout --all clears all platforms."""
        from typer.testing import CliRunner

        from src.cli.main import app

        with patch(
            "src.crawler_auth.cookie_store.CookieStore.__init__",
            return_value=None,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.clear",
        ) as mock_clear:
            runner = CliRunner()
            result = runner.invoke(app, ["auth", "logout", "--all"])
            assert result.exit_code == 0
            assert "all platforms" in result.output
            # Should be called once per platform (5 platforms)
            assert mock_clear.call_count == 5

    def test_auth_logout_requires_option(self):
        """Test logout without --platform or --all fails."""
        from typer.testing import CliRunner

        from src.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["auth", "logout"])
        assert result.exit_code == 1
        assert "Specify --platform or --all" in result.output

    def test_auth_import_from_cookie(self, tmp_path: Path):
        from typer.testing import CliRunner

        from src.cli.main import app

        with patch(
            "src.crawler_auth.cookie_store.CookieStore.__init__",
            return_value=None,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.update",
            return_value={"z_c0": "abc", "__zse_ck": "def"},
        ) as mock_update:
            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "auth",
                    "import",
                    "--platform",
                    "zhihu",
                    "--cookie",
                    "z_c0=abc; __zse_ck=def",
                ],
            )
            assert result.exit_code == 0
            assert "Imported 2 cookie(s)" in result.output
            mock_update.assert_called_once()
            assert mock_update.call_args.args[1] == {
                "z_c0": "abc",
                "__zse_ck": "def",
            }

    def test_auth_import_from_clipboard(self):
        from typer.testing import CliRunner

        from src.cli.main import app

        with patch(
            "src.crawler_auth.cookie_store.CookieStore.__init__",
            return_value=None,
        ), patch(
            "src.crawler_auth.cookie_store.CookieStore.update",
            return_value={"z_c0": "abc"},
        ), patch(
            "src.crawler_auth.read_clipboard",
            return_value="z_c0=abc",
        ):
            runner = CliRunner()
            result = runner.invoke(
                app,
                ["auth", "import", "--platform", "zhihu"],
            )
            assert result.exit_code == 0
            assert "Reading cookies from clipboard" in result.output

    def test_auth_import_invalid_cookie(self):
        from typer.testing import CliRunner

        from src.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["auth", "import", "--platform", "zhihu", "--cookie", "not-a-cookie"],
        )
        assert result.exit_code == 1
        assert "No valid cookies" in result.output


# =============================================================================
# TestWebExtractorFallback
# =============================================================================


class TestWebExtractorFallback:
    """Tests for authenticated fallback in web extractor."""

    async def test_fallback_on_403_with_cookies(self, tmp_path: Path):
        """When httpx returns 403 and cookies exist, attempt authenticated fetch."""
        from src.extractors.web import extract_from_url

        # Mock the initial httpx request to return 403
        mock_403_response = MagicMock()
        mock_403_response.status_code = 403
        mock_403_response.headers = {}

        # Mock the authenticated response
        mock_auth_response = MagicMock()
        mock_auth_response.status_code = 200
        mock_auth_response.text = "<html><head><title>Test Page</title></head><body><article><p>Authenticated content here with enough text to extract properly.</p></article></body></html>"
        mock_auth_response.headers = {"content-type": "text/html"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_403_response), \
             patch("src.crawler_auth.CookieStore") as MockStore, \
             patch("src.crawler_auth.AuthenticatedClient") as MockClient:

            mock_store_inst = MagicMock()
            mock_store_inst.load.return_value = {"z_c0": "test_token"}
            MockStore.return_value = mock_store_inst

            mock_client_inst = MagicMock()
            mock_client_inst.detect_platform.return_value = "zhihu"
            mock_client_inst.fetch = AsyncMock(return_value=mock_auth_response)
            MockClient.return_value = mock_client_inst

            content = await extract_from_url("https://www.zhihu.com/question/123")
            assert content.text is not None
            assert len(content.text) > 0
            mock_client_inst.fetch.assert_called_once_with("https://www.zhihu.com/question/123")

    async def test_fallback_on_403_without_cookies(self):
        """When httpx returns 403 but no cookies exist, raise original error."""
        from src.extractors.web import extract_from_url

        mock_403_response = MagicMock()
        mock_403_response.status_code = 403
        mock_403_response.headers = {}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_403_response), \
             patch("src.crawler_auth.CookieStore") as MockStore, \
             patch("src.crawler_auth.AuthenticatedClient") as MockClient:

            mock_store_inst = MagicMock()
            mock_store_inst.load.return_value = None  # No cookies
            MockStore.return_value = mock_store_inst

            mock_client_inst = MagicMock()
            mock_client_inst.detect_platform.return_value = "zhihu"
            MockClient.return_value = mock_client_inst

            with pytest.raises(ValueError, match="HTTP 403"):
                await extract_from_url("https://www.zhihu.com/question/123")

    async def test_fallback_on_403_unknown_platform(self):
        """When httpx returns 403 for unknown platform, raise original error."""
        from src.extractors.web import extract_from_url

        mock_403_response = MagicMock()
        mock_403_response.status_code = 403
        mock_403_response.headers = {}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_403_response), \
             patch("src.crawler_auth.CookieStore") as MockStore, \
             patch("src.crawler_auth.AuthenticatedClient") as MockClient:

            mock_store_inst = MagicMock()
            MockStore.return_value = mock_store_inst

            mock_client_inst = MagicMock()
            mock_client_inst.detect_platform.return_value = None  # Unknown platform
            MockClient.return_value = mock_client_inst

            with pytest.raises(ValueError, match="HTTP 403"):
                await extract_from_url("https://www.example.com/page")

    async def test_fallback_import_error(self):
        """When crawler_auth not installed, 403 raises normally."""
        from src.extractors.web import extract_from_url

        mock_403_response = MagicMock()
        mock_403_response.status_code = 403
        mock_403_response.headers = {}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_403_response), \
             patch.dict("sys.modules", {"src.crawler_auth": None}):

            with pytest.raises(ValueError, match="HTTP 403"):
                await extract_from_url("https://www.zhihu.com/question/123")

    async def test_no_fallback_on_200(self):
        """Normal 200 responses should not trigger fallback."""
        from src.extractors.web import extract_from_url

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><head><title>Normal Page</title></head><body><article><p>Normal content that is long enough to extract.</p></article></body></html>"
        mock_response.headers = {"content-type": "text/html"}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            content = await extract_from_url("https://www.zhihu.com/question/123")
            assert content.text is not None
            assert "Normal content" in content.text

    async def test_fallback_reports_actual_auth_status_code(self):
        """When auth fallback returns non-success, report auth status code, not original 403."""
        from src.extractors.web import extract_from_url

        mock_403_response = MagicMock()
        mock_403_response.status_code = 403
        mock_403_response.headers = {}

        # Auth response returns 429 (rate limited)
        mock_auth_response = MagicMock()
        mock_auth_response.status_code = 429

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_403_response), \
             patch("src.crawler_auth.CookieStore") as MockStore, \
             patch("src.crawler_auth.AuthenticatedClient") as MockClient:

            mock_store_inst = MagicMock()
            mock_store_inst.load.return_value = {"z_c0": "test_token"}
            MockStore.return_value = mock_store_inst

            mock_client_inst = MagicMock()
            mock_client_inst.detect_platform.return_value = "zhihu"
            mock_client_inst.fetch = AsyncMock(return_value=mock_auth_response)
            MockClient.return_value = mock_client_inst

            with pytest.raises(ValueError, match="HTTP 429"):
                await extract_from_url("https://www.zhihu.com/question/123")
