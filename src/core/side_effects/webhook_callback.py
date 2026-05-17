"""Webhook callback side effect — POST scoring results to external systems."""
from __future__ import annotations
import logging
from src.core.pipeline import PipelineContext
from src.core.side_effects.base import SideEffect

logger = logging.getLogger("side_effects.webhook_callback")


class WebhookCallbackSideEffect(SideEffect):
    """POST full scoring results to a callback URL after every score.
    
    Useful for integrating with external systems that want to receive
    scoring results asynchronously (e.g., CMS, content moderation dashboards).
    """
    
    def __init__(self, callback_url: str, include_content: bool = False):
        self._callback_url = callback_url
        self._include_content = include_content
    
    @property
    def name(self) -> str:
        return "webhook_callback"
    
    async def should_trigger(self, ctx: PipelineContext) -> bool:
        """Always trigger if we have a result."""
        return ctx.result is not None
    
    async def execute(self, ctx: PipelineContext) -> None:
        """POST the scoring result to the callback URL."""
        import httpx
        
        result = ctx.result
        content = ctx.content
        
        payload = {
            "overall_score": result.overall_score,
            "labels": result.labels,
            "summary": result.summary,
            "dimensions": result.dimensions.model_dump(),
            "model_used": result.model_used,
            "confidence": result.confidence,
            "title": content.title if content else None,
            "source_url": content.source_url if content else None,
        }
        
        if self._include_content and content:
            payload["text_preview"] = content.text[:500]
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(self._callback_url, json=payload)
                logger.debug(f"Callback to {self._callback_url}: {response.status_code}")
        except Exception as e:
            logger.warning(f"Callback to {self._callback_url} failed: {e}")
