"""Notification side effect — alerts when content scores below threshold."""
from __future__ import annotations
import logging
from src.core.pipeline import PipelineContext
from src.core.side_effects.base import SideEffect

logger = logging.getLogger("side_effects.notification")


class NotificationSideEffect(SideEffect):
    """Send notifications when scored content is below a quality threshold.
    
    Supports multiple notification channels (configured via config):
    - console (logging) — always available
    - webhook — POST to a configured URL
    - future: email, Slack, 企业微信
    """
    
    def __init__(self, threshold: float = 30.0, webhook_url: str | None = None):
        self._threshold = threshold
        self._webhook_url = webhook_url
    
    @property
    def name(self) -> str:
        return "notification"
    
    async def should_trigger(self, ctx: PipelineContext) -> bool:
        """Trigger when overall_score is below threshold."""
        if ctx.result is None:
            return False
        return ctx.result.overall_score < self._threshold
    
    async def execute(self, ctx: PipelineContext) -> None:
        """Send alert notification."""
        result = ctx.result
        content = ctx.content
        
        title = content.title if content else "Unknown"
        url = content.source_url if content else None
        score = result.overall_score
        labels = ", ".join(result.labels) if result.labels else "none"
        
        # Always log the alert
        logger.warning(
            f"LOW QUALITY ALERT: '{title}' scored {score:.0f}/100 "
            f"[labels: {labels}] {f'URL: {url}' if url else ''}"
        )
        
        # Send webhook if configured
        if self._webhook_url:
            await self._send_webhook(title, score, labels, url)
    
    async def _send_webhook(self, title: str, score: float, labels: str, url: str | None) -> None:
        """POST alert to webhook URL."""
        import httpx
        
        payload = {
            "event": "low_quality_alert",
            "title": title,
            "score": score,
            "labels": labels,
            "url": url,
            "message": f"Content '{title}' scored {score:.0f}/100 — flagged as low quality",
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self._webhook_url, json=payload)
                if response.status_code >= 400:
                    logger.warning(f"Webhook returned {response.status_code}")
        except Exception as e:
            logger.warning(f"Webhook delivery failed: {e}")
