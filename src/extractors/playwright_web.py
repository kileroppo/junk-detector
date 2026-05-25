"""Playwright-based web extractor for JavaScript-rendered (SPA) pages.

Handles sites like juejin.cn, mp.weixin.qq.com that require JS rendering.
Falls back gracefully if Playwright is not installed.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from markdownify import markdownify

from src.models.score import Content, InputType

logger = logging.getLogger("extractors.playwright")

# Domains known to require JavaScript rendering for article content
SPA_DOMAINS = {
    "juejin.cn",
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "xhslink.com",
    "xiaohongshu.com",
    "toutiao.com",
    "douyin.com",
}

# Common article content selectors ordered by specificity
ARTICLE_SELECTORS = [
    "article",
    ".article-content",
    ".post-content",
    "#article-root",  # juejin
    ".rich_media_content",  # wechat
    ".Post-RichTextContainer",  # zhihu
    ".content-detail",
    ".article-detail",
    "main",
    '[role="main"]',
]

# Elements to remove before extracting text
NOISE_SELECTORS = [
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "iframe",
    "noscript",
    ".advertisement",
    ".ad",
    ".ads",
    ".sidebar",
    ".comment",
    ".comments",
    ".related",
    ".recommended",
    ".share",
    ".social",
]


def is_spa_url(url: str) -> bool:
    """Check if the URL domain is known to require JavaScript rendering.

    Args:
        url: The URL to check.

    Returns:
        True if the domain is known to be a SPA that requires JS rendering.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        # Check if the hostname matches or is a subdomain of known SPA domains
        for domain in SPA_DOMAINS:
            if hostname == domain or hostname.endswith(f".{domain}"):
                return True
        return False
    except Exception:
        return False


async def extract_from_url_playwright(url: str, timeout_ms: int = 30000) -> Content:
    """Extract content from a URL using Playwright for JavaScript rendering.

    Launches a headless Chromium browser, navigates to the URL, waits for
    the page to finish loading (networkidle), then extracts the article content.

    Args:
        url: The URL to extract content from.
        timeout_ms: Maximum time in milliseconds to wait for page load.

    Returns:
        A Content model with extracted text, title, and metadata.

    Raises:
        ImportError: If playwright is not installed.
        TimeoutError: If page load exceeds timeout.
        ValueError: If no content could be extracted.
        RuntimeError: If the browser crashes or fails to launch.
    """
    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError(
            "Playwright is not installed. Install it with: "
            "pip install 'junk-detector[browser]' && playwright install chromium"
        )

    browser = None
    playwright_instance = None

    try:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Navigate and wait for network to settle
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PlaywrightTimeout:
            # If networkidle times out, try with domcontentloaded
            logger.warning(f"networkidle timeout for {url}, retrying with domcontentloaded")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Give extra time for JS rendering
            await page.wait_for_timeout(3000)

        # Extract title
        title = await page.title()
        if not title:
            h1_element = await page.query_selector("h1")
            if h1_element:
                title = await h1_element.inner_text()

        # Remove noise elements from the DOM
        for selector in NOISE_SELECTORS:
            try:
                await page.evaluate(
                    f"""() => {{
                        document.querySelectorAll('{selector}').forEach(el => el.remove());
                    }}"""
                )
            except Exception:
                pass  # Some selectors may not match; that's fine

        # Try to find main content using article selectors
        content_html = None
        for selector in ARTICLE_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    inner_html = await element.inner_html()
                    # Verify it has meaningful content (not just whitespace)
                    inner_text = await element.inner_text()
                    if inner_text and len(inner_text.strip()) > 50:
                        content_html = inner_html
                        logger.debug(f"Found content using selector: {selector}")
                        break
            except Exception:
                continue

        # Fall back to body if no article selector matched
        if not content_html:
            body = await page.query_selector("body")
            if body:
                content_html = await body.inner_html()
                logger.debug("Fell back to body for content extraction")

        if not content_html:
            raise ValueError(f"Could not extract any HTML content from: {url}")

        # Convert HTML to clean markdown/text
        text = markdownify(content_html, strip=["img", "a"])

        # Clean up the text
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        text = "\n".join(lines)

        if not text or len(text.strip()) < 10:
            raise ValueError(f"Extracted content is empty or too short from: {url}")

        text = text.strip()

        content = Content(
            input_type=InputType.URL,
            text=text,
            source_url=url,
            title=title or None,
        )
        content.compute_hash()

        logger.info(f"Successfully extracted {len(text)} chars from {url} via Playwright")
        return content

    except ImportError:
        raise
    except Exception as e:
        if "Target page, context or browser has been closed" in str(e):
            raise RuntimeError(f"Browser crashed while loading {url}: {e}") from e
        if "timeout" in str(e).lower():
            raise TimeoutError(f"Page load timed out for {url}: {e}") from e
        raise
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright_instance:
            try:
                await playwright_instance.stop()
            except Exception:
                pass


async def smart_extract(url: str) -> Content:
    """Intelligently extract content from a URL using the best available method.

    Auto-detects whether the URL requires JavaScript rendering (SPA sites)
    and uses Playwright if available. Falls back to httpx-based extraction
    if Playwright is not installed or fails.

    Args:
        url: The URL to extract content from.

    Returns:
        A Content model with extracted text, title, and metadata.
    """
    from src.extractors.web import extract_from_url as extract_static

    if is_spa_url(url):
        logger.info(f"SPA domain detected for {url}, attempting Playwright extraction")
        try:
            return await extract_from_url_playwright(url)
        except ImportError:
            logger.warning(
                "Playwright not installed, falling back to static extraction. "
                "Install with: pip install 'junk-detector[browser]' && playwright install chromium"
            )
            return await extract_static(url)
        except Exception as e:
            logger.warning(
                f"Playwright extraction failed for {url}: {e}. Falling back to static extraction."
            )
            return await extract_static(url)
    else:
        # For non-SPA URLs, use the faster httpx-based extractor
        return await extract_static(url)
