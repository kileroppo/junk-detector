"""Verdict generator - produces one-sentence verdict + action recommendation.

Implements the 'simple-first' UX: users see ONE sentence + ONE action by default.
"""

from __future__ import annotations

# Reading time estimation: ~400 Chinese chars per minute
_CHARS_PER_MINUTE = 400

# Action recommendations by risk profile
_ACTIONS = {
    "high_scam": "不建议转发，可能是诈骗套路",
    "high_advertorial": "核心信息约占 30%，其余为推广内容",
    "high_ai_generic": "AI 批量生成，缺乏独特见解",
    "high_emotional": "情绪操纵明显，建议冷静后再判断",
    "worth_reading": "信息密度高，建议花 {minutes} 分钟细读",
    "tool_list_valid": "工具列表类，可收藏备用",
    "news_timely": "时效性新闻，注意验证信源",
}


def generate_verdict(
    overall_score: float,
    dimensions: dict,
    content_type: str | None,
    content_text: str,
) -> dict:
    """Generate one-sentence verdict + action recommendation.

    Args:
        overall_score: The overall quality score (0-100)
        dimensions: Dict of dimension scores (scam_prob, emotional_manipulation, etc.)
        content_type: Classified content type (tool_list, news, etc.) or None
        content_text: The original content text (for reading time estimation)

    Returns:
        {
            "verdict": "one-sentence conclusion",
            "action": "specific action recommendation",
            "severity": "safe|warning|danger",
            "read_time_minutes": int
        }
    """
    # Calculate reading time
    char_count = len(content_text) if content_text else 0
    read_time = max(1, round(char_count / _CHARS_PER_MINUTE))

    # Determine severity
    if overall_score > 75:
        severity = "safe"
    elif overall_score > 40:
        severity = "warning"
    else:
        severity = "danger"

    # Find highest risk dimension
    risk_dims = {
        "scam_prob": dimensions.get("scam_prob", 0),
        "advertorial_prob": dimensions.get("advertorial_prob", 0),
        "emotional_manipulation": dimensions.get("emotional_manipulation", 0),
        "ai_generated_prob": dimensions.get("ai_generated_prob", 0),
    }
    highest_risk_dim = max(risk_dims, key=risk_dims.get)
    highest_risk_value = risk_dims[highest_risk_dim]

    # Generate verdict sentence
    if severity == "safe":
        verdict = f"内容质量良好，值得花 {read_time} 分钟阅读"
    elif severity == "warning":
        issue_map = {
            "scam_prob": "存在疑似推销话术",
            "advertorial_prob": "含有推广成分",
            "emotional_manipulation": "有情绪引导倾向",
            "ai_generated_prob": "疑似AI生成内容",
        }
        issue = issue_map.get(highest_risk_dim, "内容质量一般") if highest_risk_value > 50 else "内容质量一般"
        verdict = f"{issue}，建议批判性阅读"
    else:  # danger
        warning_map = {
            "scam_prob": "高度疑似诈骗或收割内容",
            "advertorial_prob": "大量推广内容，信息价值低",
            "emotional_manipulation": "严重情绪操纵，请保持警惕",
            "ai_generated_prob": "AI批量生成，缺乏原创价值",
        }
        verdict = warning_map.get(highest_risk_dim, "内容质量极低，不建议阅读")

    # Generate action recommendation
    if severity == "safe":
        if content_type == "tool_list":
            action = _ACTIONS["tool_list_valid"]
        elif content_type == "news":
            action = _ACTIONS["news_timely"]
        else:
            action = _ACTIONS["worth_reading"].format(minutes=read_time)
    elif severity == "danger":
        if highest_risk_value > 70 and highest_risk_dim == "scam_prob":
            action = _ACTIONS["high_scam"]
        elif highest_risk_value > 70 and highest_risk_dim == "advertorial_prob":
            action = _ACTIONS["high_advertorial"]
        elif highest_risk_value > 70 and highest_risk_dim == "emotional_manipulation":
            action = _ACTIONS["high_emotional"]
        elif highest_risk_value > 70 and highest_risk_dim == "ai_generated_prob":
            action = _ACTIONS["high_ai_generic"]
        else:
            action = "不建议花时间阅读此内容"
    else:  # warning
        if highest_risk_value > 50 and highest_risk_dim == "advertorial_prob":
            action = "注意区分推广内容和核心信息"
        elif highest_risk_value > 50 and highest_risk_dim == "emotional_manipulation":
            action = "建议冷静后再做判断"
        else:
            action = f"可选择性阅读，预计 {read_time} 分钟"

    return {
        "verdict": verdict,
        "action": action,
        "severity": severity,
        "read_time_minutes": read_time,
    }
