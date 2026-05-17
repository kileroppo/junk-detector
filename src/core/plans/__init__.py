"""Execution Plans — parallel scoring strategies.

Inspired by x-algorithm's PlanMaster pattern.
Multiple scoring plans run concurrently, results are merged.
"""
from src.core.plans.base import ScoringPlan, PlanMaster
from src.core.plans.rules_plan import RulesCheckPlan
from src.core.plans.llm_plan import LLMJudgePlan
from src.core.plans.similarity_plan import SimilarityPlan

__all__ = ["ScoringPlan", "PlanMaster", "RulesCheckPlan", "LLMJudgePlan", "SimilarityPlan"]
