"""Build template context for scoring result pages."""

from __future__ import annotations

from typing import Any

from src.core.dimension_meta import NEGATIVE_DIMENSIONS, POSITIVE_DIMENSIONS


def build_annotated_paragraphs(
    content_text: str | None,
    focus_guide: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build paragraph list with highlight status for side-by-side original view."""
    if not content_text or not focus_guide:
        return []

    from src.core.focus_guide import split_paragraphs

    paragraphs = split_paragraphs(content_text)
    if not paragraphs:
        return []

    top_nuggets = focus_guide.get("top_nuggets") or focus_guide.get("information_nuggets", [])[:3]
    must_read_indices = {n.get("index") for n in top_nuggets if n.get("index") is not None}
    reading_map: list[str] = focus_guide.get("reading_map") or []
    empty_indices = set(focus_guide.get("empty_calorie_indices") or [])

    caution_index: int | None = None
    caution = focus_guide.get("caution") or {}
    anchor = caution.get("search_anchor") or ""
    if anchor:
        for i, para in enumerate(paragraphs):
            if anchor in para:
                caution_index = i
                break

    annotated: list[dict[str, Any]] = []
    for i, para in enumerate(paragraphs):
        if i == caution_index:
            status = "caution"
        elif i in must_read_indices:
            status = "gold"
        elif reading_map and i < len(reading_map):
            status = reading_map[i]
        elif i in empty_indices:
            status = "skip"
        else:
            status = "neutral"

        if i in must_read_indices:
            label = "必看"
        elif status == "caution":
            label = "警惕"
        elif status == "skip":
            label = "可略"
        else:
            label = ""

        annotated.append(
            {
                "index": i,
                "text": para,
                "status": status,
                "label": label,
                "is_must_read": i in must_read_indices,
            }
        )

    return annotated


_STATUS_LABELS: dict[str, str] = {
    "gold": "值得看",
    "skip": "可略",
    "neutral": "正常读",
    "caution": "需警惕",
}


def _segment_position_hint(start: int, end: int, total: int) -> str:
    mid = (start + end) / 2 / max(total - 1, 1)
    if mid <= 0.25:
        return "开篇"
    if mid >= 0.75:
        return "后段"
    return "中段"


def _segment_tooltip(start: int, end: int, total: int, status: str) -> str:
    label = _STATUS_LABELS.get(status, status)
    pos = _segment_position_hint(start, end, total)
    if start == end:
        return f"第 {start + 1} 段 · {label} · {pos}"
    return f"第 {start + 1}–{end + 1} 段 · {label} · {pos}"


def _build_route_hint(segments: list[dict[str, Any]], recommendation: str) -> str:
    if recommendation == "read_carefully" or not segments:
        return ""

    hints: list[str] = []
    for seg in segments:
        status = seg["status"]
        pos = seg["position_hint"]
        if status == "gold":
            hints.append(f"{pos}重点看")
        elif status == "skip" and seg["span"] >= 2:
            hints.append(f"{pos}可跳过")
        elif status == "caution":
            hints.append(f"{pos}别全信")

    if not hints:
        return ""
    return " → ".join(hints[:4])


def build_reading_map_display(focus_guide: dict[str, Any] | None) -> dict[str, Any] | None:
    """Human-friendly reading route from paragraph-level reading_map."""
    if not focus_guide:
        return None

    reading_map: list[str] = focus_guide.get("reading_map") or []
    if len(reading_map) <= 1:
        return None

    total = len(reading_map)
    display_status = list(reading_map)

    caution = focus_guide.get("caution") or {}
    caution_index = caution.get("index")
    if caution_index is not None and 0 <= caution_index < total:
        display_status[caution_index] = "caution"

    segments: list[dict[str, Any]] = []
    i = 0
    while i < total:
        status = display_status[i]
        j = i + 1
        while j < total and display_status[j] == status:
            j += 1
        start, end = i, j - 1
        span = j - i
        segments.append(
            {
                "status": status,
                "start_index": start,
                "end_index": end,
                "span": span,
                "width_percent": round(span / total * 100, 1),
                "label": _STATUS_LABELS.get(status, status),
                "position_hint": _segment_position_hint(start, end, total),
                "tooltip": _segment_tooltip(start, end, total, status),
                "show_inline_label": span >= 2 and (span / total) >= 0.15,
            }
        )
        i = j

    gold_count = sum(1 for s in display_status if s == "gold")
    skip_count = sum(1 for s in display_status if s == "skip")
    caution_count = sum(1 for s in display_status if s == "caution")

    summary_parts = [f"全文 {total} 段"]
    if gold_count:
        summary_parts.append(f"{gold_count} 处值得看")
    if skip_count:
        summary_parts.append(f"{skip_count} 段可略")
    if caution_count:
        summary_parts.append(f"{caution_count} 处需警惕")
    saved = focus_guide.get("reading_time_saved_percent")
    if skip_count and saved:
        summary_parts.append(f"约 {saved}% 可跳过")

    recommendation = focus_guide.get("recommendation", "")
    route_hint = _build_route_hint(segments, recommendation)

    return {
        "segments": segments,
        "total_paragraphs": total,
        "summary": " · ".join(summary_parts),
        "route_hint": route_hint,
        "gold_count": gold_count,
        "skip_count": skip_count,
        "caution_count": caution_count,
        "neutral_count": total - gold_count - skip_count - caution_count,
    }


_SKIP_PATTERN_LABELS: dict[str, str] = {
    "filler": "套话",
    "transition": "过渡",
    "water": "注水",
    "vague": "空洞",
    "low_density": "低密度",
}


def _legacy_skip_headline(section: dict[str, Any]) -> str:
    reason = section.get("reason") or ""
    if "套话" in reason or "过渡" in reason:
        return "套话堆叠区"
    if "过渡" in reason:
        return "过渡铺垫段"
    return "低价值段落"


def build_skippable_display(focus_guide: dict[str, Any] | None) -> dict[str, Any] | None:
    """Enrich skippable sections for template cards."""
    if not focus_guide:
        return None

    raw_sections = focus_guide.get("skippable_sections") or []
    if not raw_sections:
        return None

    total_paras = focus_guide.get("paragraph_count") or 0
    saved_pct = focus_guide.get("reading_time_saved_percent") or 0

    enriched: list[dict[str, Any]] = []
    total_skip_paras = 0

    for section in raw_sections:
        start = section.get("start_index", 0)
        end = section.get("end_index", start)
        span = section.get("paragraph_count") or (end - start + 1)
        total_skip_paras += span

        pattern_type = section.get("pattern_type") or "low_density"
        headline = section.get("headline") or _legacy_skip_headline(section)
        skip_advice = section.get("skip_advice") or "时间紧可以略过，不影响抓重点"

        if total_paras > 0:
            range_start = int(round(start / total_paras * 100))
            range_end = int(round((end + 1) / total_paras * 100))
            range_width = max(range_end - range_start, 6)
        else:
            range_start, range_width = 0, 100

        if span == 1:
            paragraph_label = "1 段"
            index_label = f"第 {start + 1} 段"
        else:
            paragraph_label = f"{span} 段连读"
            index_label = f"第 {start + 1}–{end + 1} 段"

        enriched.append(
            {
                **section,
                "headline": headline,
                "skip_advice": skip_advice,
                "pattern_type": pattern_type,
                "pattern_label": _SKIP_PATTERN_LABELS.get(pattern_type, "可略"),
                "paragraph_count": span,
                "paragraph_label": paragraph_label,
                "index_label": index_label,
                "range_start_percent": range_start,
                "range_width_percent": min(range_width, 100 - range_start),
            }
        )

    enriched.sort(key=lambda s: s.get("start_index", 0))

    # Largest blocks first — reader cares most about where to save time
    ranked = sorted(
        enriched,
        key=lambda s: (-s.get("paragraph_count", 1), s.get("start_index", 0)),
    )
    preview_limit = 4
    preview_sections = ranked[:preview_limit]
    overflow_sections = ranked[preview_limit:]
    for section in enriched:
        section["compact_title"] = (
            f"{section['pattern_label']} · {section['position_label']} · {section['headline']}"
        )

    zone_count = len(enriched)
    summary_parts = [f"{zone_count} 处可略"]
    if total_skip_paras:
        summary_parts.append(f"涉及 {total_skip_paras} 段")
    if total_paras and total_skip_paras:
        pct = int(round(total_skip_paras / total_paras * 100))
        summary_parts.append(f"约占全文 {pct}%")
    elif saved_pct:
        summary_parts.append(f"约 {saved_pct}% 可跳过")

    return {
        "sections": enriched,
        "preview_sections": preview_sections,
        "overflow_sections": overflow_sections,
        "overflow_count": len(overflow_sections),
        "zone_count": zone_count,
        "total_skip_paragraphs": total_skip_paras,
        "summary": " · ".join(summary_parts),
    }


def score_tier(
    score: float,
    *,
    content_genre: str | None = None,
    dimensions: dict[str, float] | None = None,
) -> dict[str, str]:
    """Human-readable score band for result hero."""
    dims = dimensions or {}
    if content_genre == "roundup":
        if dims.get("scam_prob", 100) < 40 and dims.get("emotional_manipulation", 100) < 40:
            if score >= 45:
                return {"key": "reference", "label": "汇编参考", "css": "score-tier-normal"}
            if score >= 32:
                return {"key": "reference", "label": "汇编参考", "css": "score-tier-suspicious"}
    if score >= 80:
        return {"key": "quality", "label": "质量良好", "css": "score-tier-quality"}
    if score >= 60:
        return {"key": "normal", "label": "整体一般", "css": "score-tier-normal"}
    if score >= 40:
        return {"key": "suspicious", "label": "存在风险", "css": "score-tier-suspicious"}
    return {"key": "junk", "label": "高风险", "css": "score-tier-junk"}


def rule_hit_label(rule: str) -> str:
    """Map internal rule id to a short Chinese label."""
    if "scam" in rule:
        return "骗局关键词"
    if "emotional" in rule or "anxiety" in rule:
        return "情绪操纵词"
    if "punctuation" in rule:
        return "过度标点"
    if "advertorial" in rule or "promo" in rule:
        return "推广关键词"
    if "ai_generated" in rule:
        return "AI 痕迹词"
    if "combo" in rule:
        return "组合信号"
    if rule.startswith("platform_"):
        return "平台特征"
    return "其他规则"


_RULE_LABEL_DIM_KEYS: dict[str, list[str]] = {
    "骗局关键词": ["scam_prob"],
    "情绪操纵词": ["emotional_manipulation"],
    "过度标点": ["emotional_manipulation"],
    "推广关键词": ["advertorial_prob"],
    "AI 痕迹词": ["ai_generated_prob"],
    "组合信号": ["scam_prob", "emotional_manipulation", "advertorial_prob"],
    "平台特征": ["advertorial_prob"],
    "其他规则": [],
}

_DIM_LABEL_BY_KEY: dict[str, str] = {
    dim["key"]: dim["label"] for dim in POSITIVE_DIMENSIONS + NEGATIVE_DIMENSIONS
}


def build_rule_hit_display(
    rule_hits: list[str],
    dimension_evidence: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Dedupe rule hits by category label for the judgment panel."""
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for rule in rule_hits:
        label = rule_hit_label(rule)
        if label not in grouped:
            grouped[label] = []
            order.append(label)
        grouped[label].append(rule)

    items: list[dict[str, Any]] = []
    evidence = dimension_evidence or {}
    for label in order:
        dim_keys = _RULE_LABEL_DIM_KEYS.get(label, [])
        indices: list[int] = []
        seen: set[int] = set()
        for dim_key in dim_keys:
            for idx in evidence.get(dim_key, {}).get("paragraph_indices") or []:
                if idx not in seen:
                    seen.add(idx)
                    indices.append(idx)
        items.append(
            {
                "label": label,
                "rules": grouped[label],
                "dim_keys": dim_keys,
                "paragraph_indices": indices,
                "linkable": bool(indices),
            }
        )
    return items


def build_dimension_highlights(dimensions: dict[str, float]) -> dict[str, list[dict[str, Any]]]:
    """Top 1 positive + top 2 risk dimensions for compact summary."""
    positives = sorted(
        POSITIVE_DIMENSIONS,
        key=lambda dim: dimensions.get(dim["key"], 0),
        reverse=True,
    )
    negatives = sorted(
        NEGATIVE_DIMENSIONS,
        key=lambda dim: dimensions.get(dim["key"], 0),
        reverse=True,
    )
    return {
        "top_positive": [{**positives[0], "value": dimensions.get(positives[0]["key"], 0)}],
        "top_risks": [
            {**dim, "value": dimensions.get(dim["key"], 0)} for dim in negatives[:2]
        ],
    }


_NEGATIVE_DIM_STATUSES: dict[str, tuple[str, ...]] = {
    "scam_prob": ("caution",),
    "emotional_manipulation": ("caution",),
    "advertorial_prob": ("skip", "caution"),
    "ai_generated_prob": ("skip", "neutral"),
}

_POSITIVE_DIM_STATUSES: dict[str, tuple[str, ...]] = {
    dim["key"]: ("gold",) for dim in POSITIVE_DIMENSIONS
}

_NEGATIVE_LINK_THRESHOLD = 35.0
_POSITIVE_LINK_THRESHOLD = 55.0

_DIMENSION_EVIDENCE_HINTS: dict[str, str] = {
    "scam_prob": "定位原文中标记为「警惕」的风险段落",
    "emotional_manipulation": "定位原文中煽动情绪的段落",
    "advertorial_prob": "定位原文中疑似推广、水分较高的段落",
    "ai_generated_prob": "定位原文中模板化、可略读的段落",
    "originality": "定位原文中标记为「必看」的核心段落",
    "info_density": "定位原文中信息密度较高的段落",
    "reasoning_quality": "定位原文中论证较充分的段落",
    "readability": "定位原文中结构清晰的段落",
    "timeliness": "定位原文中与时效相关的段落",
}


def _indices_by_status(
    annotated_paragraphs: list[dict[str, Any]], statuses: tuple[str, ...]
) -> list[int]:
    return [p["index"] for p in annotated_paragraphs if p.get("status") in statuses]


def _indices_from_focus_guide(focus_guide: dict[str, Any] | None, dim_key: str) -> list[int]:
    if not focus_guide:
        return []

    indices: list[int] = []
    if dim_key in ("scam_prob", "emotional_manipulation", "advertorial_prob"):
        caution = focus_guide.get("caution") or {}
        if caution.get("index") is not None:
            indices.append(int(caution["index"]))

    if dim_key in _POSITIVE_DIM_STATUSES:
        nuggets = focus_guide.get("top_nuggets") or focus_guide.get("information_nuggets", [])[:3]
        for nugget in nuggets:
            if nugget.get("index") is not None:
                indices.append(int(nugget["index"]))

    if dim_key == "ai_generated_prob":
        for idx in focus_guide.get("empty_calorie_indices") or []:
            indices.append(int(idx))

    return indices


def build_dimension_evidence_map(
    *,
    dimensions: dict[str, float],
    focus_guide: dict[str, Any] | None,
    annotated_paragraphs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map each dimension to paragraph indices in the original text view."""
    if not annotated_paragraphs:
        return {}

    evidence: dict[str, dict[str, Any]] = {}
    all_dims = POSITIVE_DIMENSIONS + NEGATIVE_DIMENSIONS

    for dim in all_dims:
        key = dim["key"]
        value = float(dimensions.get(key, 0))
        is_negative = key in _NEGATIVE_DIM_STATUSES
        threshold = _NEGATIVE_LINK_THRESHOLD if is_negative else _POSITIVE_LINK_THRESHOLD
        if value < threshold:
            continue

        statuses = _NEGATIVE_DIM_STATUSES.get(key) or _POSITIVE_DIM_STATUSES.get(key, ("gold",))
        from_status = _indices_by_status(annotated_paragraphs, statuses)
        from_guide = _indices_from_focus_guide(focus_guide, key)

        merged: list[int] = []
        seen: set[int] = set()
        for idx in from_guide + from_status:
            if idx not in seen:
                seen.add(idx)
                merged.append(idx)

        if not merged:
            continue

        evidence[key] = {
            "paragraph_indices": merged[:6],
            "hint": _DIMENSION_EVIDENCE_HINTS.get(key, "在原文中查看相关段落"),
            "linkable": True,
        }

    return evidence


def _attach_evidence_to_highlights(
    highlights: dict[str, list[dict[str, Any]]],
    evidence_map: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    enriched: dict[str, list[dict[str, Any]]] = {}
    for group, dims in highlights.items():
        enriched[group] = []
        for dim in dims:
            item = dict(dim)
            item["evidence"] = evidence_map.get(dim["key"])
            enriched[group].append(item)
    return enriched


def build_paragraph_dimension_map(
    dimension_evidence: dict[str, dict[str, Any]],
) -> dict[int, list[dict[str, str]]]:
    """Reverse map: paragraph index -> related dimensions."""
    para_map: dict[int, list[dict[str, str]]] = {}
    for dim_key, ev in dimension_evidence.items():
        if not ev.get("linkable"):
            continue
        label = _DIM_LABEL_BY_KEY.get(dim_key, dim_key)
        for idx in ev.get("paragraph_indices") or []:
            bucket = para_map.setdefault(int(idx), [])
            if not any(item["key"] == dim_key for item in bucket):
                bucket.append({"key": dim_key, "label": label})
    return para_map


def enrich_annotated_paragraphs_with_dimensions(
    annotated_paragraphs: list[dict[str, Any]],
    dimension_evidence: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    para_map = build_paragraph_dimension_map(dimension_evidence)
    enriched: list[dict[str, Any]] = []
    for para in annotated_paragraphs:
        item = dict(para)
        item["related_dimensions"] = para_map.get(para["index"], [])
        enriched.append(item)
    return enriched


_RECOMMENDATION_HEADLINES: dict[str, str] = {
    "skip": "建议跳过",
    "skim": "速查即可",
    "read_carefully": "值得细读",
}

READING_ACTIONS: dict[str, dict[str, str]] = {
    "skip": {
        "label": "建议跳过",
        "emoji": "🚫",
        "css": "reading-action--skip",
        "verdict_css": "focus-verdict--skip",
    },
    "skim": {
        "label": "速查即可",
        "emoji": "📋",
        "css": "reading-action--skim",
        "verdict_css": "focus-verdict--skim",
    },
    "read": {
        "label": "值得细读",
        "emoji": "✓",
        "css": "reading-action--read",
        "verdict_css": "focus-verdict--read_carefully",
    },
    "verify": {
        "label": "谨慎核实",
        "emoji": "⚠",
        "css": "reading-action--verify",
        "verdict_css": "focus-verdict--skim",
    },
}

_GENRE_DISPLAY: dict[str, dict[str, str]] = {
    "roundup": {"label": "工具清单", "css": "genre-badge--roundup"},
}

_RISK_EXPLANATION_THRESHOLD = 50


def _format_dim_scores(dims: list[dict[str, Any]]) -> str:
    return "、".join(f"{d['label']} {d['value']:.0f}" for d in dims)


def build_reading_action(
    reading_verdict: dict[str, str],
    score_tier_dict: dict[str, str],
    *,
    content_genre: str | None = None,
    dimensions: dict[str, float] | None = None,
    overall_score: float = 50.0,
) -> dict[str, str]:
    """Primary user-facing action: skip / skim / read / verify."""
    dims = dimensions or {}
    rec = reading_verdict.get("recommendation", "")
    if rec == "skip":
        key = "skip"
    elif rec == "read_carefully":
        key = "read"
    elif rec == "skim":
        key = "skim"
    elif score_tier_dict.get("key") == "junk":
        key = "skip"
    elif score_tier_dict.get("key") == "quality":
        key = "read"
    elif content_genre == "roundup" and overall_score >= 32:
        key = "skim"
    elif score_tier_dict.get("key") in ("suspicious", "junk"):
        key = "verify"
    else:
        key = "skim"

    if dims.get("scam_prob", 0) >= 60:
        key = "skip"
    elif dims.get("scam_prob", 0) >= 45 and key == "read":
        key = "verify"
    elif dims.get("emotional_manipulation", 0) >= 70 and key == "read":
        key = "verify"

    action = dict(READING_ACTIONS[key])
    action["key"] = key
    return action


def align_display_tier(
    score_tier_dict: dict[str, str],
    reading_action: dict[str, str],
    *,
    content_genre: str | None = None,
) -> dict[str, str]:
    """Tier badge aligned with reading action — avoids 「高风险」+「速查即可」."""
    key = reading_action.get("key", "skim")
    if key == "skip":
        return {"key": "junk", "label": "建议跳过", "css": "score-tier-junk"}
    if key == "read":
        if score_tier_dict.get("key") == "quality":
            return score_tier_dict
        return {"key": "quality", "label": "质量良好", "css": "score-tier-quality"}
    if key == "verify":
        return {"key": "suspicious", "label": "谨慎阅读", "css": "score-tier-suspicious"}
    if key == "skim":
        if content_genre == "roundup":
            return {"key": "reference", "label": "汇编参考", "css": "score-tier-normal"}
        if score_tier_dict.get("key") == "junk":
            return {"key": "suspicious", "label": "可参考", "css": "score-tier-suspicious"}
        return score_tier_dict
    return score_tier_dict


def build_content_genre_display(content_genre: str | None) -> dict[str, str] | None:
    if not content_genre:
        return None
    return _GENRE_DISPLAY.get(content_genre)


def build_reading_verdict(
    focus_guide: dict[str, Any] | None,
    score_tier_dict: dict[str, str],
    overall_score: float,
    dimension_highlights: dict[str, list[dict[str, Any]]],
    *,
    content_genre: str | None = None,
) -> dict[str, str]:
    """Headline + detail for reading decision (focus guide or score fallback)."""
    from src.core.content_genre import GENRE_ROUNDUP, roundup_reading_detail, roundup_reading_headline

    if content_genre == GENRE_ROUNDUP and score_tier_dict.get("key") == "reference":
        return {
            "headline": roundup_reading_headline(),
            "detail": roundup_reading_detail(),
            "recommendation": "skim",
            "css": "focus-verdict--skim",
        }

    if focus_guide:
        recommendation = focus_guide.get("recommendation", "")
        headline = focus_guide.get("verdict_headline") or _RECOMMENDATION_HEADLINES.get(
            recommendation, score_tier_dict["label"]
        )
        detail = (
            focus_guide.get("verdict_detail")
            or focus_guide.get("tldr")
            or "下方列出必看段落与需警惕之处。"
        )
        css = f"focus-verdict--{recommendation}" if recommendation else ""
        return {"headline": headline, "detail": detail, "recommendation": recommendation, "css": css}

    top_risks = dimension_highlights.get("top_risks") or []
    max_risk = max((d.get("value", 0) for d in top_risks), default=0)
    if score_tier_dict["key"] == "quality" and max_risk < _RISK_EXPLANATION_THRESHOLD:
        return {
            "headline": "值得细读",
            "detail": "未发现明显风险信号",
            "recommendation": "read_carefully",
            "css": "focus-verdict--read_carefully",
        }

    detail = build_dimension_explanation(dimension_highlights)
    recommendation = {
        "quality": "read_carefully",
        "normal": "skim",
        "suspicious": "skim",
        "junk": "skip",
        "reference": "skim",
    }.get(score_tier_dict["key"], "skim")
    headline = _RECOMMENDATION_HEADLINES.get(recommendation, score_tier_dict["label"])
    css = {
        "quality": "focus-verdict--read_carefully",
        "normal": "focus-verdict--skim",
        "suspicious": "focus-verdict--skim",
        "junk": "focus-verdict--skip",
        "reference": "focus-verdict--skim",
    }.get(score_tier_dict["key"], "focus-verdict--skim")
    return {
        "headline": headline,
        "detail": detail,
        "recommendation": recommendation,
        "css": css,
    }


def build_dimension_explanation(dimension_highlights: dict[str, list[dict[str, Any]]]) -> str:
    """One-line summary of top risk or positive dimensions."""
    top_risks = dimension_highlights.get("top_risks") or []
    significant = [d for d in top_risks if d.get("value", 0) >= _RISK_EXPLANATION_THRESHOLD]
    if significant:
        return f"拉低分数的主要是：{_format_dim_scores(significant)}"

    top_positive = dimension_highlights.get("top_positive") or []
    if top_positive:
        return f"主要亮点：{_format_dim_scores(top_positive)}"

    return ""


def build_label_chips(labels: list[str] | None) -> list[dict[str, str]]:
    """Map label strings to chip type for template styling."""
    if not labels:
        return []

    chips: list[dict[str, str]] = []
    for label in labels:
        if "高质量" in label or "原创" in label:
            chip_type = "good"
        elif "骗" in label or "韭菜" in label:
            chip_type = "bad"
        elif "AI" in label:
            chip_type = "ai"
        else:
            chip_type = "warn"
        chips.append({"text": label, "type": chip_type})
    return chips


def build_sticky_bar_data(
    *,
    title: str | None,
    reading_verdict: dict[str, str],
    reading_action: dict[str, str],
    score: float,
    score_tier: dict[str, str],
    display_tier: dict[str, str],
    dimension_explanation: str,
    summary: str = "",
    source_url: str | None = None,
    record_id: int | None = None,
) -> dict[str, Any]:
    """Compact summary for sticky result bar and clipboard copy."""
    score_int = int(round(score))
    action_label = reading_action.get("label", reading_verdict.get("headline", ""))
    verdict_css = reading_action.get("verdict_css", reading_verdict.get("css", ""))

    copy_parts: list[str] = []
    if action_label:
        copy_parts.append(action_label)
    copy_parts.append(f"{score_int}分")
    copy_parts.append(display_tier["label"])
    detail = reading_verdict.get("detail") or ""
    if detail:
        copy_parts.append(detail)
    elif summary:
        copy_parts.append(summary)
    elif dimension_explanation:
        copy_parts.append(dimension_explanation)
    if title:
        copy_parts.append(title)
    if source_url:
        copy_parts.append(source_url)

    data: dict[str, Any] = {
        "title": title or "",
        "verdict_label": action_label,
        "verdict_css": verdict_css,
        "reading_action": reading_action,
        "score": score_int,
        "score_tier_label": display_tier["label"],
        "score_tier_css": display_tier["css"],
        "copy_text": " · ".join(copy_parts),
        "source_url": source_url,
    }
    if record_id is not None:
        data["record_id"] = record_id
    return data


def build_result_display_data(
    *,
    overall_score: float,
    dimensions: dict[str, float],
    labels: list[str] | None = None,
    summary: str = "",
    model_used: str = "",
    cost: float = 0.0,
    confidence: float = 1.0,
    scored_at: str = "",
    title: str | None = None,
    source_url: str | None = None,
    rule_hits: list[str] | None = None,
    dimension_sources: dict[str, str] | None = None,
    rule_score: float | None = None,
    rules_fired: bool | None = None,
    focus_guide: dict[str, Any] | None = None,
    content_text: str | None = None,
    content_truncated: bool = False,
    source_warning: dict[str, str] | None = None,
    content_genre: str | None = None,
) -> dict[str, Any]:
    """Assemble result dict for result.html from stored or live scoring data."""
    rule_hits = rule_hits or []
    dimension_sources = dimension_sources or {}
    llm_score = overall_score

    if rules_fired is None:
        rules_fired = bool(rule_hits)

    score_divergence = abs(rule_score - llm_score) if rule_score is not None else 0.0
    divergence_warning = score_divergence > 20 and rules_fired

    annotated_paragraphs = build_annotated_paragraphs(content_text, focus_guide)
    reading_map_display = build_reading_map_display(focus_guide)
    skippable_display = build_skippable_display(focus_guide)
    if content_genre is None and content_text:
        from src.core.content_genre import detect_content_genre

        content_genre = detect_content_genre(content_text)

    primary_score = llm_score if rules_fired else overall_score
    score_tier_dict = score_tier(
        primary_score, content_genre=content_genre, dimensions=dimensions
    )
    dimension_highlights = build_dimension_highlights(dimensions)
    dimension_evidence = build_dimension_evidence_map(
        dimensions=dimensions,
        focus_guide=focus_guide,
        annotated_paragraphs=annotated_paragraphs,
    )
    dimension_highlights = _attach_evidence_to_highlights(dimension_highlights, dimension_evidence)
    annotated_paragraphs = enrich_annotated_paragraphs_with_dimensions(
        annotated_paragraphs, dimension_evidence
    )
    reading_verdict = build_reading_verdict(
        focus_guide,
        score_tier_dict,
        primary_score,
        dimension_highlights,
        content_genre=content_genre,
    )
    reading_action = build_reading_action(
        reading_verdict,
        score_tier_dict,
        content_genre=content_genre,
        dimensions=dimensions,
        overall_score=primary_score,
    )
    reading_verdict = {
        **reading_verdict,
        "headline": reading_action["label"],
        "css": reading_action.get("verdict_css", reading_verdict.get("css", "")),
    }
    display_tier = align_display_tier(
        score_tier_dict, reading_action, content_genre=content_genre
    )
    content_genre_display = build_content_genre_display(content_genre)
    dimension_explanation = build_dimension_explanation(dimension_highlights)
    label_chips = build_label_chips(labels)
    sticky_bar = build_sticky_bar_data(
        title=title,
        reading_verdict=reading_verdict,
        reading_action=reading_action,
        score=primary_score,
        score_tier=score_tier_dict,
        display_tier=display_tier,
        dimension_explanation=dimension_explanation,
        summary=summary,
        source_url=source_url,
    )

    return {
        "overall_score": overall_score,
        "primary_score": primary_score,
        "score_tier": display_tier,
        "raw_score_tier": score_tier_dict,
        "dimensions": dimensions,
        "dimension_highlights": dimension_highlights,
        "dimension_evidence": dimension_evidence,
        "reading_verdict": reading_verdict,
        "reading_action": reading_action,
        "content_genre_display": content_genre_display,
        "dimension_explanation": dimension_explanation,
        "sticky_bar": sticky_bar,
        "label_chips": label_chips,
        "rule_hit_display": build_rule_hit_display(rule_hits, dimension_evidence),
        "labels": labels or [],
        "summary": summary,
        "model_used": model_used,
        "cost": cost,
        "confidence": confidence,
        "scored_at": scored_at[:19] if scored_at else "",
        "title": title,
        "source_url": source_url,
        "focus_guide": focus_guide,
        "content_text": content_text,
        "content_truncated": content_truncated,
        "annotated_paragraphs": annotated_paragraphs,
        "reading_map_display": reading_map_display,
        "skippable_display": skippable_display,
        "rule_hits": rule_hits,
        "dimension_sources": dimension_sources,
        "rule_score": rule_score,
        "llm_score": llm_score,
        "score_divergence": score_divergence,
        "divergence_warning": divergence_warning,
        "rules_fired": rules_fired,
        "source_warning": source_warning,
        "content_genre": content_genre,
    }


def build_result_display_data_from_record(record: dict) -> dict[str, Any]:
    """Build display data from a database query record."""
    return build_result_display_data(
        overall_score=record["overall_score"],
        dimensions=record.get("dimensions", {}),
        labels=record.get("labels", []),
        summary=record.get("summary", ""),
        model_used=record.get("model_used", ""),
        cost=record.get("cost", 0),
        confidence=record.get("confidence", 1.0),
        scored_at=record.get("scored_at", ""),
        title=record.get("title"),
        source_url=record.get("source_url"),
        rule_hits=record.get("rule_hits", []),
        dimension_sources=record.get("dimension_sources", {}),
        rule_score=record.get("rule_score"),
        rules_fired=record.get("rules_fired"),
        focus_guide=record.get("focus_guide"),
        content_text=record.get("content_text"),
        content_truncated=record.get("content_truncated", False),
    )
