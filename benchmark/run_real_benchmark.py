#!/usr/bin/env python3
"""Run benchmark against real-data labeled dataset.

This benchmark tests the rules engine against 100 hand-labeled
real-world Chinese content samples across multiple categories.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.rules import apply_rules, should_skip_llm


def load_dataset(dataset_path: Path) -> list[dict]:
    """Load labeled JSONL dataset."""
    samples = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def classify_sample(text: str) -> str:
    """Classify a sample using the rules engine.

    Classification logic:
    - If should_skip_llm returns True AND max junk dimension >= 70: predict "junk"
    - If any dimension_override >= 50 but < 70: predict "borderline"
    - Otherwise: predict "quality"
    """
    rule_result = apply_rules(text)
    skip_llm, reason = should_skip_llm(rule_result, text)

    # Get max junk-related dimension score
    junk_dimensions = ["scam_prob", "advertorial_prob", "emotional_manipulation"]
    max_junk_score = max(
        (rule_result.dimension_overrides.get(dim, 0.0) for dim in junk_dimensions),
        default=0.0,
    )

    # If rules are confident enough to skip LLM and max junk score is high
    if skip_llm and max_junk_score >= 70:
        return "junk"

    # Check for borderline: any junk dimension between 50 and 70
    any_borderline = any(
        50 <= rule_result.dimension_overrides.get(dim, 0.0) < 70
        for dim in junk_dimensions
    )
    if any_borderline:
        return "borderline"

    # Also check if high score but not skip_llm (still suspicious)
    if max_junk_score >= 70:
        return "junk"

    return "quality"


def compute_class_metrics(
    true_labels: list[str], predicted_labels: list[str], target_class: str
) -> dict:
    """Compute precision, recall, F1 for a specific class."""
    tp = sum(
        1
        for t, p in zip(true_labels, predicted_labels)
        if t == target_class and p == target_class
    )
    fp = sum(
        1
        for t, p in zip(true_labels, predicted_labels)
        if t != target_class and p == target_class
    )
    fn = sum(
        1
        for t, p in zip(true_labels, predicted_labels)
        if t == target_class and p != target_class
    )

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}


def run_benchmark(samples: list[dict]) -> dict:
    """Run the benchmark and collect all results."""
    true_labels = []
    predicted_labels = []
    per_category = defaultdict(lambda: {"correct": 0, "total": 0, "predictions": []})
    false_positives = []  # quality content flagged as junk
    false_negatives = []  # junk content missed (predicted as quality)

    for sample in samples:
        text = sample["text"]
        true_label = sample["label"]
        category = sample["category"]

        predicted = classify_sample(text)
        true_labels.append(true_label)
        predicted_labels.append(predicted)

        # Track per-category
        per_category[category]["total"] += 1
        per_category[category]["predictions"].append(predicted)
        if predicted == true_label:
            per_category[category]["correct"] += 1

        # Track errors
        if true_label == "quality" and predicted == "junk":
            false_positives.append(
                {"text": text[:80], "category": category, "predicted": predicted}
            )
        elif true_label == "junk" and predicted == "quality":
            false_negatives.append(
                {"text": text[:80], "category": category, "predicted": predicted}
            )

    # Compute per-class metrics
    classes = ["junk", "borderline", "quality"]
    class_metrics = {}
    for cls in classes:
        class_metrics[cls] = compute_class_metrics(true_labels, predicted_labels, cls)

    # Overall accuracy
    correct = sum(1 for t, p in zip(true_labels, predicted_labels) if t == p)
    accuracy = correct / len(samples)

    return {
        "accuracy": accuracy,
        "class_metrics": class_metrics,
        "per_category": dict(per_category),
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "total_samples": len(samples),
    }


def print_results(results: dict) -> None:
    """Print results to terminal."""
    print("=" * 60)
    print("REAL DATA BENCHMARK RESULTS")
    print("=" * 60)
    print(f"\nTotal samples: {results['total_samples']}")
    print(f"Overall accuracy: {results['accuracy']:.4f}")
    print()

    # Per-class metrics
    print(f"{'Class':<12} {'Precision':>10} {'Recall':>10} {'F1':>10} {'TP':>5} {'FP':>5} {'FN':>5}")
    print("-" * 60)
    for cls in ["junk", "borderline", "quality"]:
        m = results["class_metrics"][cls]
        print(
            f"{cls:<12} {m['precision']:>10.4f} {m['recall']:>10.4f} "
            f"{m['f1']:>10.4f} {m['tp']:>5} {m['fp']:>5} {m['fn']:>5}"
        )

    # Per-category breakdown
    print()
    print("-" * 60)
    print("Per-Category Breakdown:")
    print(f"{'Category':<20} {'Correct':>8} {'Total':>8} {'Accuracy':>10}")
    print("-" * 60)
    for cat, stats in sorted(results["per_category"].items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0
        print(f"  {cat:<18} {stats['correct']:>8} {stats['total']:>8} {acc:>10.4f}")

    # False positives
    print()
    print("-" * 60)
    if results["false_positives"]:
        print(f"False Positives (quality flagged as junk): {len(results['false_positives'])}")
        for fp in results["false_positives"]:
            print(f"  [{fp['category']}] {fp['text']}...")
    else:
        print("False Positives: None")

    # False negatives
    print()
    if results["false_negatives"]:
        print(f"False Negatives (junk missed): {len(results['false_negatives'])}")
        for fn in results["false_negatives"]:
            print(f"  [{fn['category']}] {fn['text']}...")
    else:
        print("False Negatives: None")

    print()


def write_results_md(results: dict, output_path: Path) -> None:
    """Write results to markdown file."""
    lines = []
    lines.append("# Real Data Benchmark Results")
    lines.append("")
    lines.append("> Tested against 100 hand-labeled real-world Chinese content samples.")
    lines.append("> This benchmark measures rules-engine-only detection accuracy on")
    lines.append("> realistic content without LLM assistance.")
    lines.append("")

    # Overall metrics table
    lines.append("## Overall Metrics")
    lines.append("")
    lines.append(f"- **Total samples**: {results['total_samples']}")
    lines.append(f"- **Overall accuracy**: {results['accuracy']:.4f}")
    lines.append("")
    lines.append("| Metric | Junk | Borderline | Quality |")
    lines.append("|--------|------|------------|---------|")
    jm = results["class_metrics"]["junk"]
    bm = results["class_metrics"]["borderline"]
    qm = results["class_metrics"]["quality"]
    lines.append(f"| Precision | {jm['precision']:.4f} | {bm['precision']:.4f} | {qm['precision']:.4f} |")
    lines.append(f"| Recall | {jm['recall']:.4f} | {bm['recall']:.4f} | {qm['recall']:.4f} |")
    lines.append(f"| F1 | {jm['f1']:.4f} | {bm['f1']:.4f} | {qm['f1']:.4f} |")
    lines.append("")

    # Per-category breakdown
    lines.append("## Per-Category Breakdown")
    lines.append("")
    lines.append("| Category | Correct | Total | Accuracy |")
    lines.append("|----------|---------|-------|----------|")
    for cat, stats in sorted(results["per_category"].items()):
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0
        lines.append(f"| {cat} | {stats['correct']} | {stats['total']} | {acc:.4f} |")
    lines.append("")

    # False positives
    lines.append("## False Positives (quality content flagged as junk)")
    lines.append("")
    if results["false_positives"]:
        for fp in results["false_positives"]:
            lines.append(f"- **[{fp['category']}]** {fp['text']}...")
    else:
        lines.append("None - no quality content was incorrectly flagged as junk.")
    lines.append("")

    # False negatives
    lines.append("## False Negatives (junk content missed)")
    lines.append("")
    if results["false_negatives"]:
        for fn in results["false_negatives"]:
            lines.append(f"- **[{fn['category']}]** {fn['text']}...")
    else:
        lines.append("None - all junk content was correctly identified.")
    lines.append("")

    # Weaknesses
    lines.append("## Weaknesses")
    lines.append("")
    lines.append("Honest assessment of where the rules engine fails:")
    lines.append("")

    # Analyze weaknesses from data
    weaknesses = []

    bm_metrics = results["class_metrics"]["borderline"]
    if bm_metrics["recall"] < 0.3:
        weaknesses.append(
            "- **Borderline detection is weak**: The rules engine is binary by nature "
            "(matches or not), making it poor at identifying ambiguous content that falls "
            "between junk and quality."
        )

    if results["false_negatives"]:
        missed_cats = defaultdict(int)
        for fn in results["false_negatives"]:
            missed_cats[fn["category"]] += 1
        for cat, count in missed_cats.items():
            weaknesses.append(
                f"- **Misses in {cat}**: {count} samples from this category were not detected. "
                f"The rules may need more patterns for this content type."
            )

    if results["false_positives"]:
        fp_cats = defaultdict(int)
        for fp in results["false_positives"]:
            fp_cats[fp["category"]] += 1
        for cat, count in fp_cats.items():
            weaknesses.append(
                f"- **False alarms on {cat}**: {count} legitimate {cat} samples were incorrectly flagged. "
                f"Rules may be too aggressive for content in this domain."
            )

    # Always note the borderline limitation
    weaknesses.append(
        "- **Rules cannot assess nuance**: Content quality often depends on context, "
        "intent, and factual accuracy that keyword matching cannot capture. "
        "The LLM fallback is essential for borderline cases."
    )
    weaknesses.append(
        "- **No semantic understanding**: Rules match surface patterns. A well-written "
        "scam that avoids common keywords will evade detection."
    )

    lines.extend(weaknesses)
    lines.append("")

    # Confusion details section
    lines.append("## Confusion Details")
    lines.append("")
    lines.append("Examples of misclassified content:")
    lines.append("")
    if results["false_positives"] or results["false_negatives"]:
        if results["false_positives"]:
            lines.append("### False Positives (good content flagged)")
            lines.append("")
            for fp in results["false_positives"][:5]:
                lines.append(f"- **[{fp['category']}]** `{fp['text'][:60]}...`")
                lines.append(f"  - Predicted: {fp['predicted']}, Expected: quality")
                lines.append(f"  - Why: Rules matched keywords that appear in legitimate context")
            lines.append("")
        if results["false_negatives"]:
            lines.append("### False Negatives (junk content missed)")
            lines.append("")
            for fn in results["false_negatives"][:5]:
                lines.append(f"- **[{fn['category']}]** `{fn['text'][:60]}...`")
                lines.append(f"  - Predicted: {fn['predicted']}, Expected: junk")
                lines.append(f"  - Why: Content avoids typical keyword patterns")
            lines.append("")
    else:
        lines.append("No misclassifications between junk and quality classes in this run.")
        lines.append("")

    # Comparison notes section
    lines.append("## Comparison Notes")
    lines.append("")
    lines.append("### 鉴真 vs 人工审核 vs Perspective API")
    lines.append("")
    lines.append("| 方法 | 优势 | 劣势 |")
    lines.append("|------|------|------|")
    lines.append("| 鉴真 (规则引擎) | 毫秒级响应, 零成本, 隐私安全 | 无法理解语义, 依赖关键词覆盖 |")
    lines.append("| 鉴真 (规则+LLM) | 高准确率, 语义理解 | 有 API 成本, 响应较慢 |")
    lines.append("| 人工审核 | 最高准确率, 理解上下文 | 成本高, 不可扩展, 有主观性 |")
    lines.append("| Perspective API | 多语言, 成熟稳定 | 针对英文优化, 中文效果有限, 需要网络 |")
    lines.append("")
    lines.append("> **方法论说明**: 本基准仅测试鉴真规则引擎部分。")
    lines.append("> 完整的对比测试需要在相同数据集上运行各系统,")
    lines.append("> 目前我们没有 Perspective API 的中文测试结果作为对照。")
    lines.append("> 上表为定性分析,非定量对比。")
    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    """Run the real data benchmark."""
    # Load dataset
    dataset_path = Path(__file__).parent / "real_data" / "labeled_100.jsonl"
    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path}")
        sys.exit(1)

    samples = load_dataset(dataset_path)
    print(f"Loaded {len(samples)} samples")

    # Run benchmark
    results = run_benchmark(samples)

    # Print results
    print_results(results)

    # Write results markdown
    results_path = Path(__file__).parent / "real_data" / "results.md"
    write_results_md(results, results_path)
    print(f"Results written to {results_path}")


if __name__ == "__main__":
    main()
