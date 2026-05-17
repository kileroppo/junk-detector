"""LLM Judge plan — runs the LLM scoring."""
from __future__ import annotations
import logging
from src.core.plans.base import ScoringPlan, PlanResult
from src.models.score import ScoringConfig

logger = logging.getLogger("plans.llm")


class LLMJudgePlan(ScoringPlan):
    """Execute LLM-based content evaluation.
    
    The most expensive plan — calls an external LLM API.
    Can be skipped if rules cover all dimensions with high confidence.
    """
    
    def __init__(self, config: ScoringConfig | None = None, language: str = "zh"):
        self._config = config or ScoringConfig()
        self._language = language
    
    @property
    def name(self) -> str:
        return "llm_judge"
    
    async def should_run(self, text: str, **kwargs) -> bool:
        """Skip if rules already covered everything with high confidence."""
        skip_llm = kwargs.get("skip_llm", False)
        return not skip_llm
    
    async def execute(self, text: str, **kwargs) -> PlanResult:
        """Run LLM judge and return ScoreResult data."""
        from src.core.llm_judge import judge
        
        result = await judge(text, self._config, language=self._language)
        
        return PlanResult(
            plan_name=self.name,
            success=True,
            data={
                "score_result": result.model_dump(),
                "overall_score": result.overall_score,
                "dimensions": result.dimensions.model_dump(),
                "labels": result.labels,
                "summary": result.summary,
                "confidence": result.confidence,
                "model_used": result.model_used,
                "cost": result.cost,
            },
        )
