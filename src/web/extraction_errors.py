"""User-facing messages when URL / page extraction fails."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FetchErrorInfo:
    """Structured fetch / parse failure for Web UI."""

    title: str
    reason: str
    hints: tuple[str, ...]
    level: str = "error"  # error | warning
    detail: str | None = None
    url: str | None = None
    code: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_fetch_error(exc: BaseException, url: str | None = None) -> FetchErrorInfo:
    """Map extractor exceptions to plain-language guidance."""
    msg = str(exc).strip()
    lower = msg.lower()
    url_display = url or _extract_url_from_message(msg)

    if isinstance(exc, TimeoutError) or "timed out" in lower or "timeout" in lower:
        return FetchErrorInfo(
            title="网页打开超时",
            reason="服务器在规定时间内没有返回页面内容。",
            hints=(
                "请检查网络是否正常，或稍后再试。",
                "部分网站访问较慢，可换网络环境后重试。",
                "若链接来自微信等 App，请确认已在浏览器中可正常打开。",
            ),
            detail=msg if msg else None,
            url=url_display,
            code="timeout",
        )

    if "404" in msg or "not found" in lower:
        return FetchErrorInfo(
            title="页面不存在",
            reason="该链接返回了 404，可能已删除或地址有误。",
            hints=(
                "请核对链接是否复制完整（含 https://）。",
                "在浏览器中打开同一链接，确认是否能正常访问。",
            ),
            detail=msg if msg else None,
            url=url_display,
            code="not_found",
        )

    if (
        "403" in msg
        or "auth login" in lower
        or "拒绝了访问" in msg
        or "cookie" in lower and "login" in lower
    ):
        hints = (
            "该站点通常需要登录后才能阅读正文。",
            "可在「设置 → 平台 Cookie」导入登录态后重试。",
            "或在终端执行对应平台的 auth import / login 命令。",
        )
        if "auth login" in lower or "junk-detector auth" in msg:
            detail = msg
        else:
            detail = msg if msg else None
        return FetchErrorInfo(
            title="需要登录才能访问",
            reason="网站拒绝了未登录的访问（HTTP 403）。",
            hints=hints,
            level="warning",
            detail=detail,
            url=url_display,
            code="auth_required",
        )

    if "could not extract" in lower or "empty or too short" in lower or "无法提取" in msg:
        return FetchErrorInfo(
            title="未能提取正文",
            reason="页面已打开，但没有识别到可评分的文章正文。",
            hints=(
                "确认链接指向的是文章/帖子详情页，而不是首页或列表页。",
                "部分页面依赖 JavaScript 渲染，可能需要先登录该平台。",
                "可尝试复制正文到「文本」标签页直接评分。",
            ),
            detail=msg if msg else None,
            url=url_display,
            code="empty_content",
        )

    if "non-html" in lower or "content-type" in lower:
        return FetchErrorInfo(
            title="链接不是网页文章",
            reason="该地址返回的不是 HTML 网页（可能是文件下载、API 等）。",
            hints=(
                "请使用浏览器能直接阅读的文章链接。",
                "PDF、图片、视频等链接暂不支持自动解析。",
            ),
            detail=msg if msg else None,
            url=url_display,
            code="not_html",
        )

    if "failed to fetch" in lower or "requesterror" in lower or "connect" in lower:
        return FetchErrorInfo(
            title="无法连接该网站",
            reason="请求未能成功发出或中途断开。",
            hints=(
                "请检查网络、代理或防火墙设置。",
                "确认链接可在浏览器中正常打开。",
                "若仅个别站点失败，可能是对方服务器暂时不可用。",
            ),
            detail=msg if msg else None,
            url=url_display,
            code="network",
        )

    if "http " in lower or "returned http" in lower:
        status = _parse_http_status(msg)
        reason = (
            f"服务器返回了 HTTP {status}，无法获取页面内容。"
            if status
            else "服务器返回了错误状态码，无法获取页面内容。"
        )
        return FetchErrorInfo(
            title="网页访问被拒绝",
            reason=reason,
            hints=(
                "请在浏览器中打开同一链接，查看是否需要登录或验证。",
                "部分站点会拦截自动化访问，可尝试导入 Cookie 后重试。",
            ),
            detail=msg if msg else None,
            url=url_display,
            code="http_error",
        )

    return FetchErrorInfo(
        title="链接解析失败",
        reason="无法从该链接获取可评分的内容。",
        hints=(
            "请在浏览器中确认链接可正常打开。",
            "若页面需登录，请先在设置中配置平台 Cookie。",
            "也可将正文复制到「文本」标签页进行评分。",
        ),
        detail=msg if msg else None,
        url=url_display,
        code="unknown",
    )


def _extract_url_from_message(msg: str) -> str | None:
    for token in msg.split():
        if token.startswith(("http://", "https://")):
            return token.rstrip(".,;)")
    return None


def _parse_http_status(msg: str) -> str | None:
    for part in msg.replace(":", " ").split():
        if part.isdigit() and 400 <= int(part) < 600:
            return part
    return None
