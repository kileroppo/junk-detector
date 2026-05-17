"""Base classes for the side effects system."""
from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

from src.core.pipeline import PipelineContext

logger = logging.getLogger("side_effects")


class SideEffect(ABC):
    """Abstract base for all side effects."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this side effect."""
        ...
    
    @abstractmethod
    async def should_trigger(self, ctx: PipelineContext) -> bool:
        """Determine if this side effect should run for the given context."""
        ...
    
    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> None:
        """Execute the side effect. Must not raise — failures are logged and swallowed."""
        ...


class SideEffectRunner:
    """Runs all registered side effects concurrently after scoring.
    
    Fire-and-forget pattern: all side effects run in parallel,
    failures are logged but never propagate to the caller.
    """
    
    def __init__(self, effects: list[SideEffect] | None = None):
        self._effects: list[SideEffect] = effects or []
    
    def register(self, effect: SideEffect) -> "SideEffectRunner":
        """Register a new side effect. Returns self for chaining."""
        self._effects.append(effect)
        return self
    
    async def run_all(self, ctx: PipelineContext) -> None:
        """Run all applicable side effects concurrently.
        
        Each effect is checked with should_trigger() first,
        then execute() is called. Failures are caught and logged.
        """
        tasks = []
        for effect in self._effects:
            try:
                if await effect.should_trigger(ctx):
                    tasks.append(self._safe_execute(effect, ctx))
            except Exception as e:
                logger.warning(f"Error checking trigger for '{effect.name}': {e}")
        
        if tasks:
            await asyncio.gather(*tasks)
            logger.debug(f"Executed {len(tasks)} side effect(s)")
    
    async def _safe_execute(self, effect: SideEffect, ctx: PipelineContext) -> None:
        """Execute a single side effect with full error isolation."""
        try:
            await effect.execute(ctx)
            logger.debug(f"Side effect '{effect.name}' completed")
        except Exception as e:
            logger.error(f"Side effect '{effect.name}' failed: {type(e).__name__}: {e}")
