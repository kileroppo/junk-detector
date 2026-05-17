"""Base classes for execution plans."""
from __future__ import annotations
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("plans")


@dataclass
class PlanResult:
    """Result from a single plan execution."""
    plan_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    execution_time_ms: float = 0.0


class ScoringPlan(ABC):
    """Abstract base for a scoring plan."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        ...
    
    @abstractmethod
    async def execute(self, text: str, **kwargs) -> PlanResult:
        """Execute this plan and return results."""
        ...
    
    async def should_run(self, text: str, **kwargs) -> bool:
        """Override to conditionally skip this plan. Default: always run."""
        return True


class PlanMaster:
    """Orchestrates multiple scoring plans in parallel.
    
    Inspired by x-algorithm's PlanMaster.exec() pattern.
    All plans run concurrently via asyncio.gather().
    Results are collected and merged.
    """
    
    def __init__(self, plans: list[ScoringPlan] | None = None):
        self._plans: list[ScoringPlan] = plans or []
    
    def register(self, plan: ScoringPlan) -> "PlanMaster":
        """Register a plan. Returns self for chaining."""
        self._plans.append(plan)
        return self
    
    async def execute_all(self, text: str, **kwargs) -> list[PlanResult]:
        """Execute all applicable plans concurrently.
        
        Plans that fail are included in results with success=False.
        """
        # Filter to plans that should run
        plans_to_run = []
        for plan in self._plans:
            try:
                if await plan.should_run(text, **kwargs):
                    plans_to_run.append(plan)
            except Exception as e:
                logger.warning(f"Error checking should_run for '{plan.name}': {e}")
        
        if not plans_to_run:
            return []
        
        # Run all plans concurrently
        tasks = [self._safe_execute(plan, text, **kwargs) for plan in plans_to_run]
        results = await asyncio.gather(*tasks)
        
        logger.info(
            f"PlanMaster executed {len(results)} plans: "
            f"{sum(1 for r in results if r.success)} succeeded, "
            f"{sum(1 for r in results if not r.success)} failed"
        )
        return results
    
    async def _safe_execute(self, plan: ScoringPlan, text: str, **kwargs) -> PlanResult:
        """Execute a plan with timing and error isolation."""
        start = time.perf_counter()
        try:
            result = await plan.execute(text, **kwargs)
            result.execution_time_ms = (time.perf_counter() - start) * 1000
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(f"Plan '{plan.name}' failed: {e}")
            return PlanResult(
                plan_name=plan.name,
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )
