"""Platform-specific authentication implementations."""
from __future__ import annotations

from .bilibili import BilibiliAuth
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

__all__ = [
    "BilibiliAuth",
    "PLATFORMS",
    "WechatAuth",
    "WeiboAuth",
    "XiaohongshuAuth",
    "ZhihuAuth",
]
