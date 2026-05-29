"""Minimal Python SDK for the 鉴真 (Jianzhen) content quality API.

Usage:
    from sdk.python import JianzhenClient

    client = JianzhenClient(api_key="your-key")
    result = client.score("日入过万 加微信领取")
    print(result["verdict"])  # "junk"
"""
from __future__ import annotations

from typing import Any, Optional

import httpx


class JianzhenClient:
    """Client for the 鉴真 content quality detection API.

    Args:
        api_key: API key for authentication (optional for free tier).
        base_url: API base URL. Defaults to http://localhost:8000.
        timeout: Request timeout in seconds. Defaults to 30.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["X-API-Key"] = api_key

    def score(self, text: str, title: Optional[str] = None) -> dict[str, Any]:
        """Score text content for quality.

        Args:
            text: The text content to analyze.
            title: Optional title for context.

        Returns:
            Dict with scoring result including overall_score, dimensions, labels, etc.

        Raises:
            httpx.HTTPStatusError: If the API returns an error status.
            httpx.ConnectError: If the API is unreachable.
        """
        payload: dict[str, Any] = {"text": text}
        if title:
            payload["title"] = title

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/score",
                json=payload,
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    def score_url(self, url: str) -> dict[str, Any]:
        """Score content from a URL.

        Args:
            url: The URL to fetch and analyze.

        Returns:
            Dict with scoring result.
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/score",
                json={"url": url},
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    def health(self) -> dict[str, Any]:
        """Check API health status.

        Returns:
            Dict with health information (status, version, uptime, etc.)
        """
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/health",
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    def demo(self, text: Optional[str] = None) -> dict[str, Any]:
        """Try the demo endpoint (no auth required).

        Args:
            text: Optional text to score. Uses default sample if not provided.

        Returns:
            Dict with demo scoring result.
        """
        params = {}
        if text:
            params["text"] = text

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                f"{self.base_url}/demo",
                params=params,
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()
