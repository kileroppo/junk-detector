"""Focus Guide generation module - heuristic analysis of AI-generated content.

Analyzes scored content and produces a FocusGuide with reading recommendations,
suspicious paragraphs, detected AI patterns, TL;DR, and information nuggets.
All analysis is purely heuristic - no LLM calls required.
"""

from __future__ import annotations

import re
import statistics
from typing import Optional

from src.models.focus_guide import (
    AIPattern,
    FocusGuide,
    InformationNugget,
    ParagraphSnippet,
    ReadingCaution,
    RhythmFingerprintModel,
    SkippableSection,
    SuspiciousParagraph,
)
from src.models.score import ScoreResult

# ---------------------------------------------------------------------------
# Constants: pattern lists for detection
# ---------------------------------------------------------------------------

# Chinese formulaic transition phrases
_CN_TRANSITIONS = [
    "首先",
    "其次",
    "再次",
    "最后",
    "综上所述",
    "总而言之",
    "值得注意的是",
    "不可否认",
    "此外",
    "另外",
    "与此同时",
    "一方面",
    "另一方面",
]

# English formulaic transition phrases
_EN_TRANSITIONS = [
    "firstly",
    "secondly",
    "thirdly",
    "in conclusion",
    "it is worth noting",
    "furthermore",
    "moreover",
    "in addition",
    "on the other hand",
    "nevertheless",
    "in summary",
    "to summarize",
    "all in all",
]

# Chinese generic filler phrases
_CN_FILLERS = [
    "众所周知",
    "不言而喻",
    "毋庸置疑",
    "在当今社会",
    "随着科技的发展",
    "随着社会的发展",
    "随着时代的发展",
    "随着经济的发展",
    "随着互联网的发展",
    "在这个信息化时代",
    "在这个快速发展的时代",
    "不得不说",
    "毫无疑问",
    "显而易见",
]

# Pattern to match "随着...的发展" generically
_CN_SUIZHE_PATTERN = re.compile(r"随着.{1,10}的发展")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return paragraphs


def split_paragraphs(text: str) -> list[str]:
    """Public API: split text into paragraphs (same logic as focus guide)."""
    return _split_paragraphs(text)


def _position_label(index: int, total: int) -> str:
    """Human-readable position in the article (not paragraph numbers)."""
    if total <= 1:
        return "全文"
    ratio = index / max(total - 1, 1)
    if ratio <= 0.12:
        return "开篇"
    if ratio <= 0.35:
        return "前部"
    if ratio <= 0.65:
        return "中部"
    if ratio <= 0.88:
        return "后部"
    return "结尾"


def _position_percent(index: int, total: int) -> int:
    """Approximate vertical position as percentage through the article."""
    if total <= 1:
        return 50
    return int(round((index + 0.5) / total * 100))


def _paragraph_preview(para: str, max_len: int = 52) -> str:
    """First words of a paragraph — the anchor a reader actually recognizes."""
    text = re.sub(r"\s+", " ", para.strip())
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^[-*•]\s*", "", text)
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "…"


def _unique_search_anchor(para: str, full_text: str, min_len: int = 10, max_len: int = 22) -> str:
    """Pick a short substring that appears only once in the full article."""
    text = re.sub(r"\s+", " ", para.strip())
    text = re.sub(r"^#+\s*", "", text)
    if not text:
        return ""
    upper = min(max_len, len(text))
    lower = min(min_len, upper)
    for length in range(upper, lower - 1, -1):
        candidate = text[:length]
        if candidate and full_text.count(candidate) == 1:
            return candidate
    return text[:lower] if len(text) >= lower else text


def _extract_evidence(para: str, limit: int = 3) -> list[str]:
    """Pull matched filler/transition phrases from the paragraph itself."""
    found: list[str] = []
    for filler in _CN_FILLERS:
        if filler in para:
            found.append(filler)
    for match in _CN_SUIZHE_PATTERN.findall(para):
        if match not in found:
            found.append(match)
    for transition in _CN_TRANSITIONS:
        if transition in para and transition not in found:
            found.append(transition)
    return found[:limit]


def _nugget_why_read(para: str) -> str:
    """Explain why this paragraph is worth reading, tied to its content."""
    nums = re.findall(r"\d+[\d.%]*", para)
    quotes = re.findall(r'[「『"]([^」』"]{4,30})[」』"]', para)
    if quotes:
        return f"引用/观点: {quotes[0]}"
    if len(nums) >= 2:
        return f"含具体数据: {'、'.join(nums[:3])}"
    if nums:
        return f"提到关键数字 {nums[0]}"
    sentences = _split_sentences(para)
    if sentences and len(sentences[0]) > 12:
        return f"核心表述: {sentences[0][:40]}{'…' if len(sentences[0]) > 40 else ''}"
    return "信息密度相对较高的一段"


def _skip_reason_with_evidence(para: str) -> tuple[str, list[str]]:
    """Skip reason citing actual matched phrases from the paragraph."""
    evidence = _extract_evidence(para)
    if evidence:
        joined = "、".join(f"「{e}」" for e in evidence[:3])
        return f"出现套话/过渡词 {joined}", evidence
    if not _has_specifics(para) and len(para) > 50:
        return "全段无数据、无引用，多为泛泛而谈", evidence
    if _count_transitions(para) >= 1:
        return "以过渡句为主，不承载新信息", evidence
    return "信息密度低，读完收获有限", evidence


def _group_consecutive_indices(indices: list[int]) -> list[tuple[int, int]]:
    """Merge consecutive paragraph indices into ranges."""
    if not indices:
        return []
    sorted_idx = sorted(set(indices))
    groups: list[tuple[int, int]] = []
    start = end = sorted_idx[0]
    for idx in sorted_idx[1:]:
        if idx == end + 1:
            end = idx
        else:
            groups.append((start, end))
            start = end = idx
    groups.append((start, end))
    return groups


def _skip_reason_for_paragraph(para: str) -> str:
    """Brief reason why this block is skippable."""
    reason, _ = _skip_reason_with_evidence(para)
    return reason


def _analyze_skip_block(
    paragraphs: list[str], start: int, end: int
) -> tuple[str, str, str, str, list[str]]:
    """Classify a skippable block: headline, reason, advice, pattern_type, evidence."""
    block = paragraphs[start : end + 1]
    span = len(block)
    evidence: list[str] = []
    for para in block:
        for item in _extract_evidence(para):
            if item not in evidence:
                evidence.append(item)
    evidence = evidence[:5]

    transition_hits = sum(_count_transitions(p) for p in block)
    has_specifics = any(_has_specifics(p) for p in block)

    if len(evidence) >= 2:
        headline = "套话堆叠区" if span >= 2 else "典型套话段"
        pattern_type = "filler"
        joined = "、".join(f"「{e}」" for e in evidence[:3])
        reason = f"命中 {len(evidence)} 处空泛表述，如 {joined}"
        skip_advice = "跳过不影响理解文章主线"
    elif transition_hits >= 2 or (transition_hits >= 1 and not has_specifics):
        headline = "过渡铺垫段" if span == 1 else "连续过渡段"
        pattern_type = "transition"
        reason = "主要在承上启下，几乎不增加新信息"
        skip_advice = "跳至下一段精华内容即可"
    elif span >= 3:
        headline = "连续注水区"
        pattern_type = "water"
        reason = f"连续 {span} 段缺少数据、案例或明确观点"
        skip_advice = "整段可略，节省最多阅读时间"
    elif not has_specifics:
        headline = "空洞铺陈"
        pattern_type = "vague"
        reason = "泛泛而谈，读完后很难复述具体事实"
        skip_advice = "扫标题或首句即可，不必细读"
    else:
        headline = "低信息段落"
        pattern_type = "low_density"
        reason, para_evidence = _skip_reason_with_evidence(block[0])
        if para_evidence and para_evidence not in evidence:
            evidence = list(dict.fromkeys(evidence + para_evidence))[:5]
        skip_advice = "时间紧可以先略过"

    return headline, reason, skip_advice, pattern_type, evidence


def _skip_block_preview(paragraphs: list[str], start: int, end: int) -> str:
    """Preview text for a skippable block — recognizable opening + span hint."""
    first = _paragraph_preview(paragraphs[start], max_len=48)
    if start == end:
        return first
    return f"{first} …（共 {end - start + 1} 段同类内容）"


def _build_skippable_sections(
    paragraphs: list[str], empty_indices: list[int], full_text: str
) -> list[SkippableSection]:
    """Turn raw indices into grouped, preview-backed skip advice."""
    total = len(paragraphs)
    sections: list[SkippableSection] = []
    for start, end in _group_consecutive_indices(empty_indices):
        preview_para = paragraphs[start]
        headline, reason, skip_advice, pattern_type, evidence = _analyze_skip_block(
            paragraphs, start, end
        )
        span = end - start + 1
        sections.append(
            SkippableSection(
                start_index=start,
                end_index=end,
                preview=_skip_block_preview(paragraphs, start, end),
                search_anchor=_unique_search_anchor(preview_para, full_text),
                reason=reason,
                evidence=evidence,
                position_label=_position_label(start, total),
                position_percent=_position_percent(start, total),
                headline=headline,
                skip_advice=skip_advice,
                pattern_type=pattern_type,
                paragraph_count=span,
            )
        )
    sections.sort(key=lambda s: (s.start_index, -(s.end_index - s.start_index)))
    return sections


def _build_verdict(
    recommendation: str,
    score_result: ScoreResult,
    nugget_count: int,
    skip_ratio: float,
) -> tuple[str, str]:
    """Human-readable verdict headline + detail."""
    dims = score_result.dimensions
    if recommendation == "skip":
        return (
            "建议别读完",
            f"全文约 {skip_ratio:.0f}% 为水分段落"
            + (f"；软文倾向 {dims.advertorial_prob:.0f}%" if dims.advertorial_prob >= 50 else "")
            + "。只看下方必看即可。",
        )
    if recommendation == "skim":
        return (
            "速查即可",
            f"精华集中在 {nugget_count} 处"
            + (f"；AI 痕迹 {dims.ai_generated_prob:.0f}%" if dims.ai_generated_prob >= 40 else "")
            + "。不必逐段细读。",
        )
    return (
        "整体可读",
        f"以下 {min(nugget_count, 3)} 处信息密度最高，优先阅读。",
    )


def _pick_caution(
    paragraphs: list[str],
    full_text: str,
    nuggets: list[InformationNugget],
    skippable_sections: list[SkippableSection],
    score_result: ScoreResult,
) -> Optional[ReadingCaution]:
    """Pick one skepticism warning grounded in score + content."""
    dims = score_result.dimensions

    if dims.advertorial_prob >= 55:
        target = nuggets[0] if nuggets else None
        preview = target.preview if target else ""
        para = paragraphs[target.index] if target and target.index < len(paragraphs) else ""
        return ReadingCaution(
            headline="别当作客观评测",
            message=(
                f"软文概率 {dims.advertorial_prob:.0f}%，"
                "参数与价格段可能是作者/厂商希望你看到的内容，需交叉验证。"
            ),
            preview=preview,
            search_anchor=target.search_anchor if target else _unique_search_anchor(para, full_text),
        )

    if dims.scam_prob >= 45:
        return ReadingCaution(
            headline="别轻信收益承诺",
            message=f"骗局风险 {dims.scam_prob:.0f}%，文中若有'稳赚/躺赚'类表述请直接忽略。",
        )

    # Spec-sheet nugget: many numbers but no judgment language
    judgment_markers = ("但", "然而", "问题", "缺点", "不足", "遗憾", "体验", "认为", "评价", "一般")
    for nugget in nuggets[:3]:
        para = paragraphs[nugget.index]
        num_count = len(re.findall(r"\d+", para))
        if num_count >= 3 and not any(m in para for m in judgment_markers):
            return ReadingCaution(
                headline="别被参数带跑",
                message="该段数字密集但缺乏独立判断，可能是通稿/公关核心话术。",
                preview=nugget.preview,
                search_anchor=nugget.search_anchor,
            )

    if skippable_sections:
        biggest = max(skippable_sections, key=lambda s: s.end_index - s.start_index)
        span = biggest.end_index - biggest.start_index + 1
        if span >= 3:
            return ReadingCaution(
                headline="别硬啃全文",
                message=f"从「{biggest.position_label}」起连续 {span} 段重复水分，读完性价比很低。",
                preview=biggest.preview,
                search_anchor=biggest.search_anchor,
            )

    return None


def _build_snippets(
    paragraphs: list[str],
    full_text: str,
    top_nuggets: list[InformationNugget],
    caution: Optional[ReadingCaution],
    skippable_sections: list[SkippableSection],
    max_snippets: int = 8,
) -> list[ParagraphSnippet]:
    """Build inline excerpt panel — only paragraphs the reader needs to see."""
    seen: set[int] = set()
    snippets: list[ParagraphSnippet] = []

    def _add(index: int, status: str, label: str, anchor: str) -> None:
        if index in seen or index >= len(paragraphs):
            return
        seen.add(index)
        text = paragraphs[index]
        display = text if len(text) <= 280 else text[:277] + "…"
        snippets.append(
            ParagraphSnippet(
                index=index,
                text=display,
                status=status,
                search_anchor=anchor or _unique_search_anchor(text, full_text),
                label=label,
            )
        )

    for n in top_nuggets:
        _add(n.index, "gold", "必看", n.search_anchor)

    if caution and caution.search_anchor:
        for i, para in enumerate(paragraphs):
            if caution.search_anchor in para:
                _add(i, "caution", "警惕", caution.search_anchor)
                break

    for section in skippable_sections[:3]:
        if len(snippets) >= max_snippets:
            break
        _add(section.start_index, "skip", "可略", section.search_anchor)

    return snippets[:max_snippets]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (handles Chinese and English punctuation)."""
    # Split on Chinese and English sentence-ending punctuation
    parts = re.split(r"[。！？.!?]+", text)
    return [s.strip() for s in parts if s.strip()]


def _has_specifics(text: str) -> bool:
    """Check if text contains specific data: numbers, dates, proper nouns, etc."""
    # Numbers (including percentages, monetary values)
    if re.search(r"\d+", text):
        return True
    # Quoted text (specific references)
    if re.search(r'[""「」『』\'"]', text):
        return True
    # Specific name patterns (capitalized words in English)
    if re.search(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)+", text):
        return True
    return False


def _count_filler_phrases(text: str) -> int:
    """Count occurrences of generic filler phrases in text."""
    count = 0
    for filler in _CN_FILLERS:
        count += text.count(filler)
    # Also count the generic pattern
    count += len(_CN_SUIZHE_PATTERN.findall(text))
    return count


def _count_transitions(text: str) -> int:
    """Count formulaic transition phrases in text."""
    text_lower = text.lower()
    count = 0
    for t in _CN_TRANSITIONS:
        if t in text:
            count += 1
    for t in _EN_TRANSITIONS:
        if t in text_lower:
            count += 1
    return count


def _information_density_score(paragraph: str) -> float:
    """Score a paragraph's information density (0.0 to 1.0).

    Higher means more genuine information content.
    """
    score = 0.0

    # Has numbers/data
    if re.search(r"\d+", paragraph):
        score += 0.3

    # Has specific names or references
    if re.search(r'[""「」『』]', paragraph):
        score += 0.2

    # Has capitalized proper nouns (English)
    if re.search(r"[A-Z][a-z]+(?:\s[A-Z][a-z]+)+", paragraph):
        score += 0.2

    # Penalize filler phrases
    filler_count = _count_filler_phrases(paragraph)
    score -= filler_count * 0.2

    # Penalize very short paragraphs (less likely to contain info)
    if len(paragraph) < 20:
        score -= 0.2

    # Bonus for longer, substantive paragraphs
    if len(paragraph) > 100 and _has_specifics(paragraph):
        score += 0.2

    # Spec-sheet paragraphs: many numbers but no independent judgment
    judgment_markers = (
        "但", "然而", "问题", "缺点", "不足", "遗憾", "体验", "认为", "评价",
        "超过", "低于", "预期", "一般", "遗憾",
    )
    num_count = len(re.findall(r"\d+", paragraph))
    marketing_markers = ("售价", "元起", "GB", "Pro", "像素", "英寸", "起售", "版本")
    if (
        num_count >= 3
        and not any(m in paragraph for m in judgment_markers)
        and any(m in paragraph for m in marketing_markers)
    ):
        score -= 0.15

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Pattern detection functions
# ---------------------------------------------------------------------------


def _detect_uniform_structure(paragraphs: list[str]) -> Optional[AIPattern]:
    """Detect if paragraphs have suspiciously uniform lengths."""
    if len(paragraphs) < 3:
        return None

    lengths = [len(p) for p in paragraphs]
    mean_len = statistics.mean(lengths)

    if mean_len == 0:
        return None

    std_dev = statistics.stdev(lengths) if len(lengths) > 1 else 0

    # If std deviation is < 20% of mean, flag as uniform
    if std_dev < mean_len * 0.2:
        return AIPattern(
            pattern_name="uniform_structure",
            description="段落长度高度一致，标准差仅为均值的{:.0f}%，典型AI生成特征".format(
                (std_dev / mean_len) * 100 if mean_len > 0 else 0
            ),
            examples=[
                f"段落长度范围: {min(lengths)}-{max(lengths)}字, 均值: {mean_len:.0f}字"
            ],
        )
    return None


def _detect_formulaic_transitions(paragraphs: list[str]) -> Optional[AIPattern]:
    """Detect formulaic transition patterns typical of AI writing."""
    transition_examples = []
    total_transitions = 0

    for para in paragraphs:
        for t in _CN_TRANSITIONS:
            if t in para:
                transition_examples.append(f"...{t}...")
                total_transitions += 1
        para_lower = para.lower()
        for t in _EN_TRANSITIONS:
            if t in para_lower:
                transition_examples.append(f"...{t}...")
                total_transitions += 1

    # Flag if more than 30% of paragraphs start with transitions
    para_start_count = 0
    for para in paragraphs:
        para_stripped = para.strip()
        for t in _CN_TRANSITIONS + _EN_TRANSITIONS:
            if para_stripped.lower().startswith(t.lower()):
                para_start_count += 1
                break

    threshold = max(2, len(paragraphs) * 0.3)
    if total_transitions >= threshold or para_start_count >= 3:
        return AIPattern(
            pattern_name="formulaic_transitions",
            description=f"检测到{total_transitions}处公式化过渡词，{para_start_count}个段落以过渡词开头",
            examples=transition_examples[:5],
        )
    return None


def _detect_repetitive_starters(paragraphs: list[str]) -> Optional[AIPattern]:
    """Detect if >30% of sentences start with the same pattern."""
    all_sentences = []
    for para in paragraphs:
        all_sentences.extend(_split_sentences(para))

    if len(all_sentences) < 5:
        return None

    # Get first 4 characters of each sentence as a starter pattern
    starters: dict[str, int] = {}
    for sent in all_sentences:
        if len(sent) >= 4:
            starter = sent[:4]
            starters[starter] = starters.get(starter, 0) + 1

    # Check if any starter appears in >30% of sentences
    threshold = len(all_sentences) * 0.3
    for starter, count in starters.items():
        if count >= threshold and count >= 3:
            return AIPattern(
                pattern_name="repetitive_starters",
                description=f"超过{count}/{len(all_sentences)}个句子以相似模式开头",
                examples=[f'"{starter}..." 出现{count}次'],
            )
    return None


def _detect_filler_phrases(paragraphs: list[str]) -> Optional[AIPattern]:
    """Detect generic filler phrases common in AI-generated Chinese text."""
    filler_examples = []
    total_fillers = 0

    full_text = "\n".join(paragraphs)

    for filler in _CN_FILLERS:
        count = full_text.count(filler)
        if count > 0:
            total_fillers += count
            filler_examples.append(filler)

    # Check the generic pattern
    suizhe_matches = _CN_SUIZHE_PATTERN.findall(full_text)
    for match in suizhe_matches:
        if match not in [f for f in _CN_FILLERS if "随着" in f]:
            total_fillers += 1
            filler_examples.append(match)

    if total_fillers >= 2:
        return AIPattern(
            pattern_name="generic_fillers",
            description=f"检测到{total_fillers}处空泛套话，缺乏具体信息",
            examples=filler_examples[:5],
        )
    return None


def _detect_lack_of_specifics(paragraphs: list[str]) -> Optional[AIPattern]:
    """Detect paragraphs without concrete data, examples, or specifics."""
    vague_count = 0
    for para in paragraphs:
        if not _has_specifics(para) and len(para) > 30:
            vague_count += 1

    if len(paragraphs) > 0 and vague_count / len(paragraphs) > 0.5:
        return AIPattern(
            pattern_name="lack_of_specifics",
            description=f"{vague_count}/{len(paragraphs)}个段落缺少具体数据、日期或实例",
            examples=["多数段落仅包含笼统描述，未引用具体来源或数据"],
        )
    return None


# ---------------------------------------------------------------------------
# TL;DR generation (extractive)
# ---------------------------------------------------------------------------


def _is_primarily_english(text: str) -> bool:
    """Check if text is primarily English/ASCII based.

    Heuristic: if more than 50% of non-whitespace characters are ASCII
    letters, digits, or common punctuation, treat as English.
    """
    if not text:
        return False
    ascii_count = sum(1 for c in text if c.isascii() and (c.isalnum() or c == ' '))
    return ascii_count > len(text) * 0.5


def _generate_tldr(paragraphs: list[str]) -> str:
    """Generate a TL;DR by picking the most information-dense sentences."""
    all_sentences = []
    for para in paragraphs:
        all_sentences.extend(_split_sentences(para))

    if not all_sentences:
        return ""

    # Score each sentence by information density
    scored = []
    for sent in all_sentences:
        if len(sent) < 10:
            continue
        density = _information_density_score(sent)
        scored.append((density, sent))

    # Sort by density descending, pick top 2-3
    scored.sort(key=lambda x: x[0], reverse=True)
    top_sentences = [s for _, s in scored[:3]]

    if not top_sentences:
        # Fallback: just use the first substantial sentence
        for sent in all_sentences:
            if len(sent) > 20:
                return sent
        return all_sentences[0] if all_sentences else ""

    # Use language-appropriate separator
    full_text = "\n".join(paragraphs)
    separator = ". " if _is_primarily_english(full_text) else "。"
    return separator.join(top_sentences)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def _should_skip_focus_guide(score_result: ScoreResult, text: str) -> bool:
    """Skip focus guide only for short, very high-confidence quality content."""
    stripped = (text or "").strip()
    if len(stripped) < 10:
        return True
    dims = score_result.dimensions
    return (
        score_result.overall_score >= 88
        and dims.ai_generated_prob < 20
        and dims.scam_prob < 25
        and dims.emotional_manipulation < 30
        and len(stripped) < 1500
    )


def generate_focus_guide(text: str, score_result: ScoreResult) -> Optional[FocusGuide]:
    """Generate a Focus Guide for content analysis.

    Returns None if content is high quality (overall_score > 70 AND ai_generated_prob < 30).
    Uses purely heuristic analysis - no LLM calls.

    Args:
        text: The original content text.
        score_result: The scoring result from the scorer.

    Returns:
        FocusGuide or None if content doesn't need a guide.
    """
    # Only skip guide for clearly high-quality *short* pieces (long essays still get a route map)
    if _should_skip_focus_guide(score_result, text):
        return None

    # Handle empty/very short text
    if not text or len(text.strip()) < 10:
        return None

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return None

    full_text = text

    # --- Detect AI patterns ---
    ai_patterns: list[AIPattern] = []

    # Rhythm fingerprint analysis
    from src.core.rhythm_fingerprint import analyze_rhythm

    rhythm = analyze_rhythm(text)
    rhythm_fingerprint = RhythmFingerprintModel(
        rhythm_uniformity=rhythm.rhythm_uniformity,
        sentence_diversity=rhythm.sentence_diversity,
        topic_drift=rhythm.topic_drift,
        paragraph_count=rhythm.paragraph_count,
        avg_paragraph_length=rhythm.avg_paragraph_length,
        length_std_dev=rhythm.length_std_dev,
    )

    if rhythm.rhythm_uniformity > 65:
        ai_patterns.append(
            AIPattern(
                pattern_name="rhythm_uniformity",
                description=f"写作节奏高度一致(均匀度{rhythm.rhythm_uniformity:.0f}/100)，段落长度变化极小",
                examples=[
                    f"段落数: {rhythm.paragraph_count}, 均长: {rhythm.avg_paragraph_length:.0f}字, 标准差: {rhythm.length_std_dev:.0f}"
                ],
            )
        )

    uniform = _detect_uniform_structure(paragraphs)
    if uniform:
        ai_patterns.append(uniform)

    transitions = _detect_formulaic_transitions(paragraphs)
    if transitions:
        ai_patterns.append(transitions)

    repetitive = _detect_repetitive_starters(paragraphs)
    if repetitive:
        ai_patterns.append(repetitive)

    fillers = _detect_filler_phrases(paragraphs)
    if fillers:
        ai_patterns.append(fillers)

    specifics = _detect_lack_of_specifics(paragraphs)
    if specifics:
        ai_patterns.append(specifics)

    # --- Classify paragraphs ---
    suspicious_paragraphs: list[SuspiciousParagraph] = []
    empty_calorie_indices: list[int] = []
    information_nuggets: list[InformationNugget] = []
    total_paras = len(paragraphs)

    for i, para in enumerate(paragraphs):
        density = _information_density_score(para)
        filler_count = _count_filler_phrases(para)
        has_data = _has_specifics(para)

        # Determine if suspicious
        reasons = []
        if filler_count >= 2:
            reasons.append("含有多处空泛套话")
        if not has_data and len(para) > 50:
            reasons.append("缺乏具体数据或实例")
        if _count_transitions(para) >= 2:
            reasons.append("过多公式化过渡词")

        if reasons:
            severity = "high" if len(reasons) >= 2 else "medium"
            suspicious_paragraphs.append(
                SuspiciousParagraph(
                    index=i,
                    reason="; ".join(reasons),
                    severity=severity,
                )
            )

        # Empty calorie: high filler ratio, no data points
        if density < 0.2 and len(para) > 20:
            empty_calorie_indices.append(i)
        elif density >= 0.3 and has_data:
            sentences = _split_sentences(para)
            summary = sentences[0][:80] if sentences else para[:80]
            information_nuggets.append(
                InformationNugget(
                    index=i,
                    summary=summary,
                    preview=_paragraph_preview(para),
                    search_anchor=_unique_search_anchor(para, full_text),
                    why_read=_nugget_why_read(para),
                    position_label=_position_label(i, total_paras),
                    position_percent=_position_percent(i, total_paras),
                    density_score=density,
                )
            )

    # --- Generate TL;DR ---
    tldr = _generate_tldr(paragraphs)

    # --- Determine recommendation ---
    ai_prob = score_result.dimensions.ai_generated_prob
    overall = score_result.overall_score
    skippable_sections = _build_skippable_sections(paragraphs, empty_calorie_indices, full_text)
    information_nuggets.sort(key=lambda n: (-n.density_score, n.index))
    top_nuggets = information_nuggets[:3]
    nugget_set = {n.index for n in information_nuggets}
    empty_set = set(empty_calorie_indices)
    reading_map = [
        "gold" if i in nugget_set else "skip" if i in empty_set else "neutral"
        for i in range(total_paras)
    ]

    # Calculate info density ratio
    info_density_ratio = (
        len(information_nuggets) / total_paras * 100 if total_paras > 0 else 50
    )

    is_roundup = getattr(score_result, "content_genre", None) == "roundup"
    if is_roundup and score_result.dimensions.scam_prob < 40:
        if overall >= 55 or info_density_ratio >= 25:
            recommendation = "skim"
        elif overall >= 40:
            recommendation = "skim"
        else:
            recommendation = "skim"
    elif ai_prob > 80 and info_density_ratio < 30:
        recommendation = "skip"
    elif ai_prob > 50 or overall < 40:
        recommendation = "skim"
    else:
        recommendation = "read_carefully"

    skip_ratio = (
        len(empty_calorie_indices) / total_paras * 100 if total_paras > 0 else 0
    )
    verdict_headline, verdict_detail = _build_verdict(
        recommendation, score_result, len(information_nuggets), skip_ratio
    )
    if (
        getattr(score_result, "content_genre", None) == "roundup"
        and score_result.dimensions.scam_prob < 40
        and score_result.dimensions.emotional_manipulation < 40
    ):
        from src.core.content_genre import roundup_reading_detail, roundup_reading_headline

        verdict_headline = roundup_reading_headline()
        verdict_detail = roundup_reading_detail()
    caution = _pick_caution(
        paragraphs, full_text, top_nuggets, skippable_sections, score_result
    )
    if caution and caution.search_anchor and caution.index is None:
        for i, para in enumerate(paragraphs):
            if caution.search_anchor in para:
                caution = caution.model_copy(update={"index": i})
                break
    snippets = _build_snippets(
        paragraphs, full_text, top_nuggets, caution, skippable_sections
    )

    # --- Calculate reading time saved ---
    reading_time_saved = (
        int(len(empty_calorie_indices) / total_paras * 100) if total_paras > 0 else 0
    )
    # Clamp to valid range
    reading_time_saved = max(0, min(100, reading_time_saved))

    return FocusGuide(
        recommendation=recommendation,
        verdict_headline=verdict_headline,
        verdict_detail=verdict_detail,
        top_nuggets=top_nuggets,
        caution=caution,
        snippets=snippets,
        suspicious_paragraphs=suspicious_paragraphs,
        ai_patterns=ai_patterns,
        tldr=tldr,
        empty_calorie_indices=empty_calorie_indices,
        information_nuggets=information_nuggets,
        skippable_sections=skippable_sections,
        paragraph_count=total_paras,
        reading_map=reading_map,
        reading_time_saved_percent=reading_time_saved,
        rhythm_fingerprint=rhythm_fingerprint,
    )
