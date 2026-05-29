"""MCP server implementation for junk-detector.

Exposes content scoring capabilities as tools callable by AI assistants
via the Model Context Protocol.
"""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("junk-detector")


@mcp.tool()
def score_text(text: str) -> dict:
    """Score text content quality. Returns dimensions, labels, and overall score."""
    try:
        from src.core.rules import apply_rules, should_skip_llm

        rule_result = apply_rules(text)
        skip, reason = should_skip_llm(rule_result, text)

        if skip:
            overrides = rule_result.dimension_overrides
            scam_prob = overrides.get("scam_prob", 0.0)
            advertorial_prob = overrides.get("advertorial_prob", 0.0)
            emotional = overrides.get("emotional_manipulation", 0.0)
            score = 100 - max(scam_prob, advertorial_prob, emotional)
            return {
                "score": round(score),
                "is_junk": score < 60,
                "dimensions": overrides,
                "matched_rules": rule_result.matched_rules,
                "summary": f"Rules engine detected: {', '.join(rule_result.matched_rules)}",
                "method": "rules_only",
            }
        else:
            # Rules not confident - still return what we have
            return {
                "score": 50,
                "is_junk": False,
                "dimensions": rule_result.dimension_overrides,
                "matched_rules": rule_result.matched_rules,
                "summary": "Rules inconclusive - LLM scoring recommended for full analysis",
                "method": "rules_partial",
            }
    except Exception as e:
        logger.error("score_text failed: %s", e)
        return {"error": str(e), "score": None, "is_junk": None}


@mcp.tool()
async def score_url(url: str) -> dict:
    """Fetch content from a URL and score its quality."""
    try:
        from src.extractors.web import extract_from_url_simple

        content = await extract_from_url_simple(url)
        result = score_text(content.text)
        result["url"] = url
        result["title"] = content.title
        return result
    except Exception as e:
        logger.error("score_url failed: %s", e)
        return {"error": str(e), "url": url, "score": None, "is_junk": None}


@mcp.tool()
def quick_check(text: str) -> dict:
    """Fast rules-only check. Returns is_junk, score, and reason."""
    try:
        result = score_text(text)
        if "error" in result:
            return {"is_junk": None, "score": None, "reason": f"Error: {result['error']}"}

        # Transform score_text result into quick_check format
        is_junk = result.get("is_junk", False)
        score_val = result.get("score", 50)

        # Build reason from matched_rules or summary
        matched = result.get("matched_rules", [])
        if matched:
            reason = f"Rules matched: {', '.join(matched)}"
        else:
            reason = result.get("summary", "No strong signals detected by rules engine")

        return {
            "is_junk": is_junk,
            "score": score_val,
            "reason": reason,
        }
    except Exception as e:
        logger.error("quick_check failed: %s", e)
        return {"is_junk": None, "score": None, "reason": f"Error: {e}"}
