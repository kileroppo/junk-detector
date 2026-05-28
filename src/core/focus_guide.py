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

    return "。".join(top_sentences)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


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
    # Don't generate guide for high-quality content
    if score_result.overall_score > 70 and score_result.dimensions.ai_generated_prob < 30:
        return None

    # Handle empty/very short text
    if not text or len(text.strip()) < 10:
        return None

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return None

    # --- Detect AI patterns ---
    ai_patterns: list[AIPattern] = []

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
            # Information nugget
            # Create a brief summary of what info is in this paragraph
            sentences = _split_sentences(para)
            summary = sentences[0][:80] if sentences else para[:80]
            information_nuggets.append(
                InformationNugget(index=i, summary=summary)
            )

    # --- Generate TL;DR ---
    tldr = _generate_tldr(paragraphs)

    # --- Determine recommendation ---
    ai_prob = score_result.dimensions.ai_generated_prob
    overall = score_result.overall_score

    # Calculate info density ratio
    total_paras = len(paragraphs)
    info_density_ratio = (
        len(information_nuggets) / total_paras * 100 if total_paras > 0 else 50
    )

    if ai_prob > 80 and info_density_ratio < 30:
        recommendation = "skip"
    elif ai_prob > 50 or overall < 40:
        recommendation = "skim"
    else:
        recommendation = "read_carefully"

    # --- Calculate reading time saved ---
    reading_time_saved = (
        int(len(empty_calorie_indices) / total_paras * 100) if total_paras > 0 else 0
    )
    # Clamp to valid range
    reading_time_saved = max(0, min(100, reading_time_saved))

    return FocusGuide(
        recommendation=recommendation,
        suspicious_paragraphs=suspicious_paragraphs,
        ai_patterns=ai_patterns,
        tldr=tldr,
        empty_calorie_indices=empty_calorie_indices,
        information_nuggets=information_nuggets,
        reading_time_saved_percent=reading_time_saved,
    )
