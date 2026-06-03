"""Platform-specific authentication implementations."""
from __future__ import annotations

from .bilibili import BilibiliAuth
from .custom import CustomPlatformAuth
from .wechat import WechatAuth
from .weibo import WeiboAuth
from .xiaohongshu import XiaohongshuAuth
from .zhihu import ZhihuAuth

PLATFORMS: dict[str, type] = {
    "zhihu": ZhihuAuth,
    "weibo": WeiboAuth,
    "xiaohongshu": XiaohongshuAuth,
    "wechat": WechatAuth,
    "bilibili": BilibiliAuth,
}

# Built-in platform IDs that cannot be overridden by custom platforms.
_BUILTIN_IDS = frozenset(PLATFORMS.keys())


def get_custom_platform_auth(config: dict) -> CustomPlatformAuth:
    """Create a CustomPlatformAuth instance from a config dict."""
    pid = config.get("id", "")
    if pid in _BUILTIN_IDS:
        raise ValueError(
            f"Platform ID {pid!r} conflicts with a built-in platform."
        )
    return CustomPlatformAuth(config)


def is_builtin_platform(platform_id: str) -> bool:
    """Check if a platform ID is a built-in platform."""
    return platform_id in _BUILTIN_IDS


__all__ = [
    "BilibiliAuth",
    "CustomPlatformAuth",
    "PLATFORMS",
    "WechatAuth",
    "WeiboAuth",
    "XiaohongshuAuth",
    "ZhihuAuth",
    "get_custom_platform_auth",
    "is_builtin_platform",
]
