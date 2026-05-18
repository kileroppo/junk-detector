"""Multimodal content extractor — handles text + images.

Extracts images from web pages and prepares them for vision LLM analysis.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

logger = logging.getLogger("extractors.multimodal")


@dataclass
class MultimodalContent:
    """Content with both text and images."""
    text: str
    image_urls: list[str] = field(default_factory=list)
    title: str | None = None
    source_url: str | None = None
    
    @property
    def has_images(self) -> bool:
        return len(self.image_urls) > 0
    
    @property
    def image_count(self) -> int:
        return len(self.image_urls)


async def extract_images_from_html(html: str, base_url: str = "", max_images: int = 5) -> list[str]:
    """Extract image URLs from HTML content.
    
    Filters out small icons, tracking pixels, and common noise.
    Returns up to max_images URLs.
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    images = []
    
    # Common patterns to skip
    skip_patterns = ["avatar", "icon", "logo", "emoji", "tracking", "pixel", "badge", "button"]
    
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        
        # Skip small/noise images
        if any(p in src.lower() for p in skip_patterns):
            continue
        
        # Skip very small images (if width/height specified)
        width = img.get("width", "")
        height = img.get("height", "")
        try:
            if width and int(width) < 100:
                continue
            if height and int(height) < 100:
                continue
        except (ValueError, TypeError):
            pass
        
        # Resolve relative URLs
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urljoin(base_url, src)
        elif not src.startswith("http"):
            src = urljoin(base_url, src)
        
        images.append(src)
        
        if len(images) >= max_images:
            break
    
    return images


async def analyze_images_with_vlm(
    image_urls: list[str],
    model: str = "gpt-4o-mini",
    api_base: str | None = None,
) -> str:
    """Analyze images using a Vision Language Model.
    
    Sends images to a VLM and gets a textual description of the visual content.
    Used to augment text-only scoring with visual context.
    
    Args:
        image_urls: List of image URLs to analyze.
        model: VLM model to use (must support vision).
        api_base: Optional API base URL.
    
    Returns:
        Textual description of the images' content and quality signals.
    """
    try:
        import litellm
    except ImportError:
        logger.warning("litellm not available for VLM analysis")
        return ""
    
    if not image_urls:
        return ""
    
    # Build message with images
    content_parts = [
        {"type": "text", "text": (
            "Analyze these images from a content quality perspective. "
            "Describe: 1) What the images show, 2) Are they original or stock photos? "
            "3) Do they add value to the article? 4) Any red flags (clickbait thumbnails, "
            "fake screenshots, misleading charts)? Reply concisely in 2-3 sentences."
        )}
    ]
    
    for url in image_urls[:3]:  # Limit to 3 images for cost
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": url},
        })
    
    messages = [{"role": "user", "content": content_parts}]
    
    try:
        kwargs = {"model": model, "messages": messages, "max_tokens": 200}
        if api_base:
            kwargs["api_base"] = api_base
        
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"VLM analysis failed: {type(e).__name__}: {e}")
        return ""


# Vision-capable models
VISION_MODELS = {
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
    "claude-sonnet-4-20250514", "claude-sonnet-4-20250514",
    "gemini-pro-vision", "gemini-1.5-pro",
}


def is_vision_model(model: str) -> bool:
    """Check if a model supports vision/image input."""
    model_lower = model.lower()
    for vm in VISION_MODELS:
        if vm in model_lower:
            return True
    return False
