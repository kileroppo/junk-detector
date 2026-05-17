"""Web content extractor — fetches and extracts article text from URLs."""

from __future__ import annotations

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

NOISE_CLASSES = [
    "nav",
    "navbar",
    "footer",
    "sidebar",
    "advertisement",
    "ad",
    "ads",
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
    "menu",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; JunkDetectorBot/0.1; +https://github.com/junk-detector)"
)

TIMEOUT = 10.0


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
        classes = " ".join(element.get("class", []))  # type: ignore[arg-type]
        el_id = element.get("id", "") or ""
        combined = f"{classes} {el_id}".lower()
        if any(noise in combined for noise in NOISE_CLASSES):
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
            return cleaned

    # Fallback: use markdownify for better structure
    html_str = str(content_element)
    markdown_text = markdownify(html_str, strip=["img", "a"])
    # Clean up the markdown output
    lines = [line.strip() for line in markdown_text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


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
    headers = {"User-Agent": USER_AGENT}

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

    # Check for other HTTP errors
    if response.status_code >= 400:
        raise ValueError(f"URL returned HTTP {response.status_code}: {url}")

    # Verify content type is HTML
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(
            f"URL returned non-HTML content (content-type: {content_type}): {url}"
        )

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Extract title before stripping noise (title is often in <head>)
    title = _extract_title(soup)

    # Strip noise elements
    _strip_noise(soup)

    # Find main content area
    main_content = _find_main_content(soup)

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
