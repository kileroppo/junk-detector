"""Friendly error handling for junk-detector.

Maps common exceptions to human-friendly Chinese error messages.
Provides graceful degradation messaging when AI scoring is unavailable.
"""

from __future__ import annotations


class FriendlyError:
    """Maps exceptions to user-friendly Chinese error messages."""

    _ERROR_MAP: list[tuple[type, str | None, str]] = [
        # (exception_type, substring_match_in_message_or_None, friendly_message)
    ]

    @classmethod
    def get_message(cls, exc: BaseException) -> str:
        """Return a human-friendly Chinese error message for the given exception.

        Args:
            exc: The exception to map.

        Returns:
            A user-friendly Chinese string describing the error.
        """
        exc_type = type(exc).__name__
        exc_msg = str(exc).lower()

        # Network connection errors
        try:
            import httpx

            if isinstance(exc, (httpx.ConnectError, ConnectionError)):
                return "\U0001f310 \u7f51\u7edc\u8fde\u63a5\u5931\u8d25\u3002\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5\u3002"
        except ImportError:
            if isinstance(exc, ConnectionError):
                return "\U0001f310 \u7f51\u7edc\u8fde\u63a5\u5931\u8d25\u3002\u8bf7\u68c0\u67e5\u7f51\u7edc\u540e\u91cd\u8bd5\u3002"

        # Timeout errors
        try:
            import httpx

            if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
                return "\u23f3 \u8bf7\u6c42\u8d85\u65f6\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"
        except ImportError:
            if isinstance(exc, TimeoutError):
                return "\u23f3 \u8bf7\u6c42\u8d85\u65f6\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"

        # API key errors
        if isinstance(exc, (KeyError, RuntimeError)):
            if "api" in exc_msg and "key" in exc_msg:
                return (
                    "\U0001f511 \u9700\u8981 API key \u624d\u80fd\u4f7f\u7528\u5b8c\u6574\u8bc4\u5206\u3002"
                    "\u8bbe\u7f6e\u65b9\u6cd5\uff1aexport DEEPSEEK_API_KEY=\u4f60\u7684key"
                )
            if isinstance(exc, KeyError) and ("api" in exc_msg or "key" in exc_msg):
                return (
                    "\U0001f511 \u9700\u8981 API key \u624d\u80fd\u4f7f\u7528\u5b8c\u6574\u8bc4\u5206\u3002"
                    "\u8bbe\u7f6e\u65b9\u6cd5\uff1aexport DEEPSEEK_API_KEY=\u4f60\u7684key"
                )

        # Invalid URL errors
        if isinstance(exc, ValueError):
            if "url" in exc_msg:
                return "\U0001f517 \u8fd9\u4e2a\u94fe\u63a5\u4f3c\u4e4e\u6709\u95ee\u9898\u3002\u8bf7\u68c0\u67e5\u662f\u5426\u5b8c\u6574\u3002"

        # Generic fallback
        return "\u274c \u51fa\u4e86\u70b9\u95ee\u9898\u3002\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002"


def get_degradation_message() -> str:
    """Return a message indicating AI scoring is unavailable and rules-only mode is active.

    Returns:
        Chinese string explaining graceful degradation to rules-only scoring.
    """
    return "\u23f3 AI \u8bc4\u5206\u6682\u65f6\u4e0d\u53ef\u7528\uff0c\u5df2\u4f7f\u7528\u89c4\u5219\u5f15\u64ce\u5feb\u901f\u8bc4\u4f30\uff08\u51c6\u786e\u5ea6\u8f83\u4f4e\uff09"
