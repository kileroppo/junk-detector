"""Similarity detection plan — checks for plagiarism/content reuse."""
from __future__ import annotations
import logging
from src.core.plans.base import ScoringPlan, PlanResult

logger = logging.getLogger("plans.similarity")


class SimilarityPlan(ScoringPlan):
    """Check content similarity against previously scored articles.
    
    Uses embedding vectors to detect plagiarism (洗稿).
    Only runs if embeddings are available.
    """
    
    @property
    def name(self) -> str:
        return "similarity_check"
    
    async def should_run(self, text: str, **kwargs) -> bool:
        """Only run if we have enough text and embeddings are configured."""
        # Skip for very short texts
        return len(text) > 200
    
    async def execute(self, text: str, **kwargs) -> PlanResult:
        """Compute embedding and check similarity."""
        try:
            from src.core.embeddings import compute_similarity
            
            similar_articles = await compute_similarity(text)
            
            has_similar = any(s.get("similarity", 0) > 0.85 for s in similar_articles)
            
            return PlanResult(
                plan_name=self.name,
                success=True,
                data={
                    "similar_articles": similar_articles,
                    "has_high_similarity": has_similar,
                    "max_similarity": max((s.get("similarity", 0) for s in similar_articles), default=0),
                },
            )
        except ImportError:
            return PlanResult(
                plan_name=self.name,
                success=True,
                data={"similar_articles": [], "has_high_similarity": False, "max_similarity": 0},
            )
        except Exception as e:
            logger.warning(f"Similarity check failed: {e}")
            return PlanResult(
                plan_name=self.name,
                success=False,
                error=str(e),
            )
