"""Explanation quality benchmark using golden explanations.

Compares system-generated explanations to human-written ideal explanations
using character bigram Jaccard similarity.
"""

from __future__ import annotations

# 10 golden explanations (sample text -> ideal explanation)
GOLDEN_EXPLANATIONS = [
    {
        "text": "日入过万 躺赚 财富自由 限时免费 加微信领取",
        "golden": "这是典型的投资诈骗话术。使用了虚假收益承诺('日入过万')、不劳而获诱惑('躺赚')和制造紧迫感('限时免费')等手法诱导受害者。",
    },
    {
        "text": "亲测有效 良心推荐 点击链接 优惠券 粉丝专属折扣",
        "golden": "这是伪装成个人体验的商业推广内容。包含推荐码、优惠券等明显的利益关联信号，作者可能从推广中获得佣金。",
    },
    {
        "text": "震惊！99%的人不知道 再不看就晚了 删前速看",
        "golden": "典型的情绪操纵标题党。利用FOMO心理和虚假紧迫感吸引点击，实际内容通常与标题不符。",
    },
    {
        "text": "月入百万不是梦 零成本创业 拉人头就能赚 保证赚钱",
        "golden": "高度疑似传销或庞氏骗局。'零成本'加'拉人头'是传销核心特征，'保证赚钱'是违法金融宣传。",
    },
    {
        "text": "好物推荐 种草 安利给大家 复制口令打开 返利",
        "golden": "含有多个软文推广信号。'种草'、'安利'结合商业链接和返利机制，属于典型的带货内容。",
    },
    {
        "text": "紧急通知 全网疯传 不看后悔一辈子 最后机会",
        "golden": "使用多重焦虑话术制造紧迫感。'紧急'、'最后机会'等词汇旨在压缩读者思考时间，促使冲动行动。",
    },
    {
        "text": "稳赚不赔 只赚不赔 暴利项目 私聊领取名额",
        "golden": "投资诈骗信号明确。'稳赚不赔'违反基本金融常识，'私聊领取'是将受害者引入私域进行精准诈骗的手段。",
    },
    {
        "text": "这款护肤品真的太好用了 推荐码XXXX 限时折扣 分销赚佣金",
        "golden": "商业推广软文。以个人体验为掩护推广产品，推荐码和分销机制表明作者直接从推广中获利。",
    },
    {
        "text": "万万没想到 细思极恐 揭秘行业黑幕 必看",
        "golden": "使用猎奇和恐惧话术吸引点击。多个情绪操纵关键词堆叠，旨在激发好奇心和焦虑感。",
    },
    {
        "text": "免费领取 一夜暴富 轻松月入十万 名额有限快来抢",
        "golden": "诈骗话术集合。虚假免费诱饵结合暴富承诺和人为稀缺感，是典型的网络投资骗局引流手段。",
    },
]


def bigram_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity based on character bigrams.

    Args:
        text_a: First text string.
        text_b: Second text string.

    Returns:
        Float between 0.0 and 1.0 representing similarity.
    """
    if not text_a or not text_b:
        return 0.0

    def get_bigrams(text: str) -> set[str]:
        return {text[i : i + 2] for i in range(len(text) - 1)}

    bigrams_a = get_bigrams(text_a)
    bigrams_b = get_bigrams(text_b)

    if not bigrams_a or not bigrams_b:
        return 0.0

    intersection = bigrams_a & bigrams_b
    union = bigrams_a | bigrams_b

    return len(intersection) / len(union)


def run_explanation_benchmark() -> dict:
    """Run the explanation quality benchmark against golden explanations.

    Uses the scoreContent-equivalent logic from the rules engine to generate
    explanations for each golden sample, then compares using bigram Jaccard similarity.

    Returns:
        Dictionary with 'average_similarity', 'scores' list, and 'total_samples'.
    """
    from src.core.rules import apply_rules

    from src.core.explainer import explain_result
    from src.models.score import DimensionScores, ScoreResult

    scores: list[float] = []

    for sample in GOLDEN_EXPLANATIONS:
        text = sample["text"]
        golden = sample["golden"]

        # Score using rules engine
        rule_result = apply_rules(text)

        # Build a mock ScoreResult for the explainer
        junk_dims = ["scam_prob", "advertorial_prob", "emotional_manipulation"]
        max_junk = max(
            (rule_result.dimension_overrides.get(d, 0.0) for d in junk_dims),
            default=0.0,
        )
        overall_score = max(0, 100 - max_junk)

        mock_score = ScoreResult(
            overall_score=overall_score,
            dimensions=DimensionScores(
                originality=50,
                info_density=50,
                reasoning_quality=50,
                readability=50,
                timeliness=50,
                ai_generated_prob=0,
                emotional_manipulation=rule_result.dimension_overrides.get(
                    "emotional_manipulation", 0
                ),
                advertorial_prob=rule_result.dimension_overrides.get(
                    "advertorial_prob", 0
                ),
                scam_prob=rule_result.dimension_overrides.get("scam_prob", 0),
            ),
            labels=[],
            summary="benchmark",
            confidence=0.0,
            model_used="rules-only",
            cost=0.0,
        )

        # Generate explanation
        generated = explain_result(mock_score, rule_result, content=text)

        # Compute similarity
        similarity = bigram_jaccard_similarity(generated, golden)
        scores.append(similarity)

    average = sum(scores) / len(scores) if scores else 0.0

    return {
        "average_similarity": round(average, 4),
        "scores": [round(s, 4) for s in scores],
        "total_samples": len(GOLDEN_EXPLANATIONS),
    }


if __name__ == "__main__":
    result = run_explanation_benchmark()
    print(f"Explanation Quality Benchmark")
    print(f"{'=' * 40}")
    print(f"Total samples: {result['total_samples']}")
    print(f"Average similarity: {result['average_similarity']:.4f}")
    print(f"\nPer-sample scores:")
    for i, score in enumerate(result["scores"]):
        print(f"  Sample {i + 1}: {score:.4f}")
