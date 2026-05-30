"""Nine-dimension labels and concise help text for UI tooltips."""

from __future__ import annotations

from typing import TypedDict


class DimensionMeta(TypedDict):
    key: str
    label: str
    description: str


POSITIVE_DIMENSIONS: list[DimensionMeta] = [
    {
        "key": "originality",
        "label": "原创性",
        "description": "是否有独特观点或第一手信息，而非洗稿、搬运或套话堆砌。",
    },
    {
        "key": "info_density",
        "label": "信息密度",
        "description": "单位篇幅内的有效信息量，干货与空话的比例。",
    },
    {
        "key": "reasoning_quality",
        "label": "论证质量",
        "description": "观点是否有依据、逻辑是否自洽，还是只有结论没有推理。",
    },
    {
        "key": "readability",
        "label": "可读性",
        "description": "结构是否清晰、层次是否合理，读起来是否顺畅。",
    },
    {
        "key": "timeliness",
        "label": "时效性",
        "description": "信息是否仍具参考价值，还是已经过时或被反复翻炒。",
    },
]

NEGATIVE_DIMENSIONS: list[DimensionMeta] = [
    {
        "key": "ai_generated_prob",
        "label": "AI生成概率",
        "description": "文风是否模板化、套话多、缺乏具体细节，像 AI 批量产出。",
    },
    {
        "key": "emotional_manipulation",
        "label": "情绪操纵",
        "description": "是否靠焦虑、恐惧、愤怒或紧迫感驱动你点击或行动。",
    },
    {
        "key": "advertorial_prob",
        "label": "软文概率",
        "description": "是否在变相推销产品、课程或服务，隐藏商业推广意图。",
    },
    {
        "key": "scam_prob",
        "label": "骗局概率",
        "description": "是否有虚假承诺、引流私聊、投资诱导等收割型话术。",
    },
]

DIMENSION_LABELS: dict[str, str] = {
    dim["key"]: dim["label"] for dim in POSITIVE_DIMENSIONS + NEGATIVE_DIMENSIONS
}
