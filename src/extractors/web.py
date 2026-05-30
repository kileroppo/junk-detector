"""Web content extractor — fetches and extracts article text from URLs."""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

from src.models.score import Content, InputType

# Elements that are typically not part of the main article content
NOISE_TAGS = [
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "iframe",
    "noscript",
    "form",
]

# Whole class/id tokens (hyphen-separated) — avoids matching "ad" inside "preload"
_NOISE_CLASS_TOKENS = frozenset(
    {
        "nav",
        "navbar",
        "footer",
        "sidebar",
        "ad",
        "ads",
        "menu",
        "qr",
        "social",
        "share",
        "comment",
        "comments",
        "related",
        "recommended",
        "popup",
        "modal",
        "cookie",
        "banner",
        "newsletter",
        "subscribe",
        "subscription",
        "breadcrumb",
        "widget",
        "preloader",
        "a11y",
    }
)

# Longer phrases: safe to match as substrings in class + id text
_NOISE_CLASS_SUBSTRINGS = [
    "advertisement",
    "accessibility",
    "lang-switch",
    "language-switch",
    "skip-link",
    "site-nav",
    "global-nav",
    "qr-code",
]

# Lines dropped from article text after DOM extraction (site chrome, i18n bars, etc.)
_BOILERPLATE_LINE_RE = re.compile(
    r"^("
    r"跳到内容|跳到导航|跳到页脚|无障碍设置|无障碍|"
    r"浅色主题|深色主题|高对比度|文字大小|行距|段距|"
    r"下划线链接|减弱动画|易读字体|大光标|重置|"
    r"订阅邮件|保持关注|"
    r"填写\s*表单|隐私政策|条款|"
    r"OK|×|news|ZH|IT|EN|FR|ES|DE|TR|RU|PT|JA"
    r")$",
    re.I,
)

_TRUNCATE_MARKERS = (
    "相关文章",
    "订阅邮件",
    "保持关注",
    "在寻找计算机工程师",
    "### 相关文章",
    "Cerca articoli",
)


def _trim_article_boilerplate(text: str) -> str:
    """Remove leading site chrome and trailing newsletter/related blocks from plain text."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line and not _BOILERPLATE_LINE_RE.match(line)]

    # Drop short language-switch runs at the top (e.g. IT EN FR …)
    while lines and len(lines[0]) <= 3 and lines[0].isalpha():
        lines.pop(0)

    # Start near first heading-like line if early lines look like nav
    for i, line in enumerate(lines[:40]):
        if len(line) >= 12 and not re.match(r"^(首页|关于|简历|博客|工具|联系方式|广告)$", line):
            if i > 0 and sum(1 for prev in lines[:i] if len(prev) < 8) >= 3:
                lines = lines[i:]
            break

    trimmed: list[str] = []
    truncate_after = int(len(lines) * 0.72) if lines else 0
    for i, line in enumerate(lines):
        if i >= truncate_after and any(
            line.startswith(marker) or line.strip() == marker for marker in _TRUNCATE_MARKERS
        ):
            break
        trimmed.append(line)

    return "\n".join(trimmed) if trimmed else text.strip()

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

TIMEOUT = 10.0


def _element_class_tokens(element: Tag) -> set[str]:
    tokens: set[str] = set()
    for cls in element.get("class") or []:
        for part in str(cls).lower().replace("_", "-").split("-"):
            if part:
                tokens.add(part)
    el_id = element.get("id")
    if el_id:
        for part in str(el_id).lower().replace("_", "-").split("-"):
            if part:
                tokens.add(part)
    return tokens


_ARTICLE_BODY_CLASS_HINTS = (
    "entry-content",
    "post-content",
    "article-content",
    "article-body",
    "post-body",
    "single-content",
    "blog-post",
)


def _is_noise_element(element: Tag) -> bool:
    classes = " ".join(element.get("class") or []).lower()
    if any(hint in classes for hint in _ARTICLE_BODY_CLASS_HINTS):
        return False
    if element.get("itemprop") == "articleBody":
        return False
    if _element_class_tokens(element) & _NOISE_CLASS_TOKENS:
        # Layout helpers like has-sidebar are not chrome sidebars
        tokens = _element_class_tokens(element)
        if tokens & {"sidebar"} and tokens & {"has", "with", "row"}:
            return False
        return True
    el_id = element.get("id") or ""
    combined = f"{classes} {el_id}".lower()
    return any(noise in combined for noise in _NOISE_CLASS_SUBSTRINGS)


def _strip_noise(soup: BeautifulSoup) -> None:
    """Remove navigation, ads, scripts, styles, and other noise elements in-place."""
    # Remove noise tags entirely
    for tag_name in NOISE_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    # Remove elements with noisy class/id names
    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        if not element.attrs:
            continue
        if _is_noise_element(element):
            element.decompose()


def _find_main_content(soup: BeautifulSoup) -> Tag | None:
    """Find the main content area of the page.

    Strategy:
    1. Look for <article> tag
    2. Look for <main> tag
    3. Look for common content div patterns (role="main", class contains "content"/"article")
    4. Fall back to the largest text block in <body>
    """
    # 1. Try <article>
    article = soup.find("article")
    if article and isinstance(article, Tag):
        return article

    # 2. Try <main>
    main = soup.find("main")
    if main and isinstance(main, Tag):
        return main

    # 3. Try role="main" or common content class names
    role_main = soup.find(attrs={"role": "main"})
    if role_main and isinstance(role_main, Tag):
        return role_main

    for class_hint in ["content", "article", "post", "entry", "story"]:
        candidates = soup.find_all(True, class_=lambda c: c and class_hint in " ".join(c).lower())
        if candidates:
            # Pick the candidate with the most text
            best = max(candidates, key=lambda el: len(el.get_text(strip=True)))
            if isinstance(best, Tag) and len(best.get_text(strip=True)) > 100:
                return best

    # 4. Fall back to largest <div> or <section> by text length
    body = soup.find("body")
    if body and isinstance(body, Tag):
        blocks = body.find_all(["div", "section"])
        if blocks:
            largest = max(blocks, key=lambda el: len(el.get_text(strip=True)))
            if isinstance(largest, Tag) and len(largest.get_text(strip=True)) > 50:
                return largest

    return None


def _pick_main_content(soup: BeautifulSoup) -> Tag | None:
    """Choose main content; fall back if the candidate block is too short."""
    main_content = _find_main_content(soup)
    if main_content and len(main_content.get_text(strip=True)) >= 400:
        return main_content
    body = soup.find("body")
    if body and isinstance(body, Tag):
        blocks = body.find_all(["article", "div", "section"])
        if blocks:
            largest = max(blocks, key=lambda el: len(el.get_text(strip=True)))
            if len(largest.get_text(strip=True)) > len(main_content.get_text(strip=True) if main_content else ""):
                return largest
    return main_content


def _extract_title(soup: BeautifulSoup) -> str | None:
    """Extract the page title from <title> tag or first <h1>."""
    title_tag = soup.find("title")
    if title_tag:
        text = title_tag.get_text(strip=True)
        if text:
            return text

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return text

    return None


def _extract_text(content_element: Tag) -> str:
    """Extract clean text from a content element.

    First tries to get readable text via get_text(). If the result is too short
    or messy, falls back to markdownify for better structure preservation.
    """
    # Try plain text extraction first
    plain_text = content_element.get_text(separator="\n", strip=True)

    # If we got reasonable text, clean it up
    if plain_text and len(plain_text) > 50:
        # Clean up excessive whitespace
        lines = [line.strip() for line in plain_text.splitlines()]
        lines = [line for line in lines if line]  # Remove empty lines
        cleaned = "\n".join(lines)
        if len(cleaned) > 50:
            return _trim_article_boilerplate(cleaned)

    # Fallback: use markdownify for better structure
    html_str = str(content_element)
    markdown_text = markdownify(html_str, strip=["img", "a"])
    # Clean up the markdown output
    lines = [line.strip() for line in markdown_text.splitlines()]
    lines = [line for line in lines if line]
    return _trim_article_boilerplate("\n".join(lines))


async def extract_from_url_simple(url: str, max_chars: int = 10000) -> Content:
    """Fallback extraction: fetch URL and strip all HTML tags.

    Uses a simple get_text() approach without article detection or noise removal.
    This is used as a fallback when the primary extract_from_url fails.

    Args:
        url: The URL to fetch and extract content from.
        max_chars: Maximum number of characters to return (default 10000).
                   If the extracted text exceeds this, it is truncated.

    Returns:
        A Content model with raw stripped text.

    Raises:
        ValueError: If the URL returns an error or no text can be extracted.
        TimeoutError: If the request times out.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise TimeoutError(f"Request timed out after {TIMEOUT}s: {url}") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Failed to fetch URL: {url} — {exc}") from exc

    if response.status_code >= 400:
        raise ValueError(f"URL returned HTTP {response.status_code}: {url}")

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Simple extraction: just get all text from body
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    if not text or len(text.strip()) == 0:
        raise ValueError(f"Could not extract any text content from: {url}")

    text = text.strip()

    # Truncate if exceeds max_chars to prevent token budget overruns
    if len(text) > max_chars:
        text = text[:max_chars]

    # Try to get title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    content = Content(
        input_type=InputType.URL,
        text=text,
        source_url=url,
        title=title,
    )
    content.compute_hash()

    return content


async def extract_from_url(url: str) -> Content:
    """Fetch a URL and extract its main article content.

    Args:
        url: The URL to fetch and extract content from.

    Returns:
        A Content model with extracted text, title, and metadata.

    Raises:
        ValueError: If the URL returns a 404 or the response is not HTML.
        TimeoutError: If the request times out.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise TimeoutError(f"Request timed out after {TIMEOUT}s: {url}") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"Failed to fetch URL: {url} — {exc}") from exc

    # Check for 404
    if response.status_code == 404:
        raise ValueError(f"URL returned 404 Not Found: {url}")

    # Check for auth-required responses (403) - attempt authenticated fallback
    if response.status_code == 403:
        fallback_success = False

        # Try 1: Use saved cookies via crawler_auth
        try:
            from src.crawler_auth import AuthenticatedClient, CookieStore

            store = CookieStore()
            client_auth = AuthenticatedClient(cookie_store=store)
            platform = client_auth.detect_platform(url)

            if platform and store.load(platform) is not None:
                auth_response = await client_auth.fetch(url)
                if auth_response.status_code < 400:
                    response = auth_response
                    fallback_success = True
        except (ImportError, Exception):
            pass

        # Try 2: Use Playwright headless browser
        if not fallback_success:
            try:
                from playwright.async_api import async_playwright

                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    html_content = await page.content()
                    await browser.close()

                # Parse with BeautifulSoup and return
                soup = BeautifulSoup(html_content, "html.parser")
                title = _extract_title(soup)
                _strip_noise(soup)
                main_content = _find_main_content(soup)
                if main_content:
                    text = _extract_text(main_content)
                else:
                    from bs4 import Tag
                    body = soup.find("body")
                    text = _extract_text(body) if body and isinstance(body, Tag) else soup.get_text(separator="\n", strip=True)

                if text and len(text.strip()) > 0:
                    content = Content(
                        input_type=InputType.URL,
                        text=text.strip(),
                        source_url=url,
                        title=title,
                    )
                    content.compute_hash()
                    return content
            except (ImportError, Exception):
                pass

        # All fallbacks failed - give helpful error message
        if not fallback_success:
            platform_name = ""
            try:
                from src.crawler_auth import AuthenticatedClient
                platform_name = AuthenticatedClient().detect_platform(url) or ""
            except ImportError:
                pass

            if platform_name:
                raise ValueError(
                    f"该网站拒绝了访问（HTTP 403）。请先登录：junk-detector auth login --platform {platform_name}"
                )
            else:
                raise ValueError(f"URL returned HTTP 403: {url}")

    # Check for other HTTP errors
    if response.status_code >= 400:
        raise ValueError(f"URL returned HTTP {response.status_code}: {url}")

    # Verify content type is HTML
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(f"URL returned non-HTML content (content-type: {content_type}): {url}")

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract title before stripping noise (title is often in <head>)
    title = _extract_title(soup)

    # Strip noise elements
    _strip_noise(soup)

    # Find main content area
    main_content = _pick_main_content(soup)

    if main_content:
        text = _extract_text(main_content)
    else:
        # Last resort: extract from body
        body = soup.find("body")
        if body and isinstance(body, Tag):
            text = _extract_text(body)
        else:
            text = soup.get_text(separator="\n", strip=True)

    if not text or len(text.strip()) == 0:
        raise ValueError(f"Could not extract any text content from: {url}")

    text = text.strip()

    content = Content(
        input_type=InputType.URL,
        text=text,
        source_url=url,
        title=title,
    )
    content.compute_hash()

    return content
