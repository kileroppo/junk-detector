"""Actionable recommendations for junk-detector scoring results.

Provides Chinese-language next-step recommendations based on content verdict and scores.
"""

from __future__ import annotations


def get_recommendation(
    verdict: str,
    scam_prob: float = 0,
    advertorial_prob: float = 0,
    overall_score: float = 50,
) -> str:
    """Return an actionable recommendation based on scoring results.

    Priority order: scam > advertorial > quality > suspicious (default).

    Args:
        verdict: The scoring verdict string (not currently used for logic, reserved).
        scam_prob: Scam probability score (0-100).
        advertorial_prob: Advertorial probability score (0-100).
        overall_score: Overall content quality score (0-100).

    Returns:
        A Chinese recommendation string with actionable next steps.
    """
    if scam_prob >= 60:
        return "\u5efa\u8bae\uff1a\u4e0d\u8981\u70b9\u51fb\u94fe\u63a5\uff0c\u4e0d\u8981\u8f6c\u8d26\uff0c\u53ef\u541112315\u4e3e\u62a5"

    if advertorial_prob >= 60:
        return "\u5efa\u8bae\uff1a\u6ce8\u610f\u6587\u4e2d\u63a8\u8350\u53ef\u80fd\u662f\u4ed8\u8d39\u5e7f\u544a"

    if overall_score > 80:
        return "\U0001f31f \u4f18\u8d28\u5185\u5bb9\uff01\u8bba\u8bc1\u4e25\u5bc6\uff0c\u6570\u636e\u7fd4\u5b9e\u3002\u5efa\u8bae\uff1a\u53ef\u4ee5\u653e\u5fc3\u5206\u4eab\u7ed9\u670b\u53cb"

    return "\u5efa\u8bae\uff1a\u8c28\u614e\u5bf9\u5f85\u6587\u4e2d\u89c2\u70b9\uff0c\u5efa\u8bae\u4ea4\u53c9\u9a8c\u8bc1\u4fe1\u606f\u6765\u6e90"
