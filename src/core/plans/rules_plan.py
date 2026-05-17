"""Rules check plan — runs deterministic rules engine."""
from __future__ import annotations
import logging
from src.core.plans.base import ScoringPlan, PlanResult

logger = logging.getLogger("plans.rules")


class RulesCheckPlan(ScoringPlan):
    """Execute the deterministic rules engine.
    
    Fast, zero-cost check for obvious patterns (scam, spam, emotional manipulation).
    """
    
    @property
    def name(self) -> str:
        return "rules_check"
    
    async def execute(self, text: str, **kwargs) -> PlanResult:
        """Run rules and return matched patterns."""
        from src.core.rules import apply_rules
        
        rule_result = apply_rules(text)
        
        return PlanResult(
            plan_name=self.name,
            success=True,
            data={
                "matched_rules": rule_result.matched_rules if hasattr(rule_result, 'matched_rules') else [],
                "dimension_overrides": rule_result.dimension_overrides if hasattr(rule_result, 'dimension_overrides') else {},
                "rule_confidence": rule_result.confidence if hasattr(rule_result, 'confidence') else {},
            },
        )
