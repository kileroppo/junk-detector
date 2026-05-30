"""Tests for src/core/errors.py - Friendly error handling."""

from src.core.errors import FriendlyError, get_degradation_message


class TestFriendlyErrorConnectionError:
    """ConnectionError should map to network failure message."""

    def test_connection_error(self):
        exc = ConnectionError("Connection refused")
        msg = FriendlyError.get_message(exc)
        assert msg == "🌐 网络连接失败。请检查网络后重试。"


class TestFriendlyErrorValueError:
    """ValueError with 'url' should map to invalid URL message."""

    def test_invalid_url(self):
        exc = ValueError("invalid url format")
        msg = FriendlyError.get_message(exc)
        assert msg == "🔗 这个链接似乎有问题。请检查是否完整。"

    def test_value_error_without_url(self):
        exc = ValueError("something else went wrong")
        msg = FriendlyError.get_message(exc)
        assert msg == "❌ 出了点问题。请稍后重试。"


class TestFriendlyErrorTimeout:
    """TimeoutError should map to timeout message."""

    def test_timeout_error(self):
        exc = TimeoutError("request timed out")
        msg = FriendlyError.get_message(exc)
        assert msg == "⏳ 请求超时，请稍后重试。"


class TestFriendlyErrorAPIKey:
    """RuntimeError mentioning API key should map to API key message."""

    def test_runtime_error_api_key(self):
        exc = RuntimeError("API key missing")
        msg = FriendlyError.get_message(exc)
        assert msg == "🔑 需要 API key 才能使用完整评分。设置方法：export DEEPSEEK_API_KEY=你的key"

    def test_key_error_api(self):
        exc = KeyError("API_KEY")
        msg = FriendlyError.get_message(exc)
        assert msg == "🔑 需要 API key 才能使用完整评分。设置方法：export DEEPSEEK_API_KEY=你的key"


class TestFriendlyErrorGeneric:
    """Generic exceptions should map to fallback message."""

    def test_generic_exception(self):
        exc = Exception("something unexpected")
        msg = FriendlyError.get_message(exc)
        assert msg == "❌ 出了点问题。请稍后重试。"

    def test_type_error(self):
        exc = TypeError("wrong type")
        msg = FriendlyError.get_message(exc)
        assert msg == "❌ 出了点问题。请稍后重试。"


class TestDegradationMessage:
    """get_degradation_message should return the degradation notice."""

    def test_degradation_message(self):
        msg = get_degradation_message()
        assert msg == "⏳ AI 评分暂时不可用，已使用规则引擎快速评估（准确度较低）"
