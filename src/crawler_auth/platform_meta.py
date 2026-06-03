"""Display metadata for platform cookie management UI."""
from __future__ import annotations

from .platforms import PLATFORMS

# Extend this dict when adding new platforms.
PLATFORM_META: dict[str, dict[str, str | list[str]]] = {
    "zhihu": {
        "label": "知乎",
        "domain": "zhihu.com",
        "hint": "需搜索页 Cookie（zhihu.com 域）",
        "guide_url": "https://www.zhihu.com/search?type=content&q=test",
        "key_cookies": ["z_c0", "__zse_ck"],
    },
    "weibo": {
        "label": "微博",
        "domain": "m.weibo.cn",
        "hint": "需 H5 移动版 Cookie（weibo.cn 域）",
        "guide_url": "https://m.weibo.cn/search?containerid=100103type%3D1%26q%3Dtest",
        "key_cookies": ["SUB", "SUBP", "_T_WM", "XSRF-TOKEN"],
    },
    "xiaohongshu": {
        "label": "小红书",
        "domain": "xiaohongshu.com",
        "hint": "登录后从 xiaohongshu.com 复制 Cookie",
        "guide_url": "https://www.xiaohongshu.com/explore",
        "key_cookies": ["a1", "webId", "web_session"],
    },
    "bilibili": {
        "label": "B站",
        "domain": "bilibili.com",
        "hint": "登录后从 bilibili.com 复制 Cookie",
        "guide_url": "https://www.bilibili.com",
        "key_cookies": ["SESSDATA", "bili_jct"],
    },
    "wechat": {
        "label": "微信/搜狗",
        "domain": "weixin.sogou.com",
        "hint": "搜狗微信搜索页 Cookie",
        "guide_url": "https://weixin.sogou.com/",
        "key_cookies": ["SNUID", "ABTEST"],
    },
}


def list_platform_ids() -> list[str]:
    """All registered platform IDs (builtin + custom), sorted."""
    from .custom_store import CustomPlatformStore

    ids = set(PLATFORMS.keys())
    for p in CustomPlatformStore().list_all():
        pid = p.get("id")
        if pid:
            ids.add(pid)
    return sorted(ids)


def get_platform_meta(platform_id: str) -> dict:
    """Return display metadata for a platform (with sensible defaults)."""
    # Check if this is a custom platform
    from .custom_store import CustomPlatformStore

    custom = CustomPlatformStore().get(platform_id)
    if custom:
        domains = custom.get("domains") or []
        return {
            "id": platform_id,
            "label": str(custom.get("label", platform_id.title())),
            "domain": domains[0] if domains else "",
            "hint": str(custom.get("hint", "从浏览器 DevTools 复制 Cookie")),
            "guide_url": str(custom.get("login_url", "")),
            "key_cookies": list(custom.get("key_cookies") or []),
            "is_custom": True,
            "validate_url": custom.get("validate_url") or "",
        }

    meta = PLATFORM_META.get(platform_id, {})
    return {
        "id": platform_id,
        "label": str(meta.get("label", platform_id.title())),
        "domain": str(meta.get("domain", "")),
        "hint": str(meta.get("hint", "从浏览器 DevTools 复制 Cookie")),
        "guide_url": str(meta.get("guide_url", "")),
        "key_cookies": list(meta.get("key_cookies", [])),
        "is_custom": False,
        "validate_url": "",
    }
