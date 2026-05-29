"""Benchmark script for junk-detector rules engine."""
import argparse
import json
import sys
from pathlib import Path

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

    Classification logic: if any dimension_override >= 60 AND its
    confidence >= 0.7, predict "junk"; else predict "quality".
    """
    rule_result = apply_rules(text)

    for dim, score in rule_result.dimension_overrides.items():
        conf = rule_result.confidence.get(dim, 0.0)
        if score >= 60 and conf >= 0.7:
            return "junk"

    return "quality"


def calculate_metrics(
    samples: list[dict],
) -> dict:
    """Run classification and calculate metrics."""
    tp = 0  # True positive: predicted junk, actually junk
    fp = 0  # False positive: predicted junk, actually quality
    tn = 0  # True negative: predicted quality, actually quality
    fn = 0  # False negative: predicted quality, actually junk

    # Per-category tracking
    category_stats: dict[str, dict[str, int]] = {}

    for sample in samples:
        text = sample["text"]
        true_label = sample["label"]
        category = sample["category"]

        predicted = classify_sample(text)

        if category not in category_stats:
            category_stats[category] = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}

        if predicted == "junk" and true_label == "junk":
            tp += 1
            category_stats[category]["tp"] += 1
        elif predicted == "junk" and true_label == "quality":
            fp += 1
            category_stats[category]["fp"] += 1
        elif predicted == "quality" and true_label == "quality":
            tn += 1
            category_stats[category]["tn"] += 1
        elif predicted == "quality" and true_label == "junk":
            fn += 1
            category_stats[category]["fn"] += 1

    # Overall metrics
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "category_stats": category_stats,
    }


def print_results(metrics: dict) -> None:
    """Print results to terminal."""
    print("=" * 60)
    print("JUNK DETECTOR BENCHMARK RESULTS")
    print("=" * 60)
    print()

    # Confusion matrix
    print("Confusion Matrix:")
    print(f"                  Predicted Junk    Predicted Quality")
    print(f"  Actual Junk     {metrics['tp']:>10}        {metrics['fn']:>10}")
    print(f"  Actual Quality  {metrics['fp']:>10}        {metrics['tn']:>10}")
    print()

    # Overall metrics
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall:    {metrics['recall']:.4f}")
    print(f"F1 Score:  {metrics['f1']:.4f}")
    print()

    # Per-category breakdown
    print("-" * 60)
    print("Per-Category Breakdown (Junk Categories):")
    print(f"{'Category':<25} {'Precision':>10} {'Recall':>10} {'TP':>5} {'FN':>5}")
    print("-" * 60)

    junk_categories = ["scam", "clickbait", "advertorial", "emotional_manipulation", "ai_slop"]
    for cat in junk_categories:
        stats = metrics["category_stats"].get(cat, {"tp": 0, "fp": 0, "fn": 0})
        cat_tp = stats["tp"]
        cat_fn = stats["fn"]
        cat_recall = cat_tp / (cat_tp + cat_fn) if (cat_tp + cat_fn) > 0 else 0.0
        # Precision for a single junk category is TP / (TP from this category)
        # since we cannot separate FPs by junk category easily
        print(f"  {cat:<23} {'N/A':>10} {cat_recall:>10.4f} {cat_tp:>5} {cat_fn:>5}")

    print()
    print("-" * 60)
    print("Per-Category Breakdown (Quality Categories - False Positive Rate):")
    print(f"{'Category':<25} {'FP':>5} {'TN':>5} {'FP Rate':>10}")
    print("-" * 60)

    quality_categories = ["news", "tech_blog", "educational", "opinion"]
    for cat in quality_categories:
        stats = metrics["category_stats"].get(cat, {"fp": 0, "tn": 0})
        cat_fp = stats["fp"]
        cat_tn = stats["tn"]
        total = cat_fp + cat_tn
        fp_rate = cat_fp / total if total > 0 else 0.0
        print(f"  {cat:<23} {cat_fp:>5} {cat_tn:>5} {fp_rate:>10.4f}")

    print()


def write_results_md(metrics: dict, output_path: Path) -> None:
    """Write results to markdown file."""
    lines = []
    lines.append("# Benchmark Results")
    lines.append("")
    lines.append("> Note: This benchmark uses a synthetic dataset generated from the same keyword patterns")
    lines.append("> used by the rules engine. These metrics measure rule coverage consistency, not real-world")
    lines.append("> detection accuracy on unseen content. For production evaluation, use independently sourced")
    lines.append("> labeled data.")
    lines.append("")
    lines.append("## Overall Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Precision | {metrics['precision']:.4f} |")
    lines.append(f"| Recall | {metrics['recall']:.4f} |")
    lines.append(f"| F1 Score | {metrics['f1']:.4f} |")
    lines.append("")
    lines.append("## Confusion Matrix")
    lines.append("")
    lines.append("| | Predicted Junk | Predicted Quality |")
    lines.append("|---|---|---|")
    lines.append(f"| Actual Junk | {metrics['tp']} | {metrics['fn']} |")
    lines.append(f"| Actual Quality | {metrics['fp']} | {metrics['tn']} |")
    lines.append("")
    lines.append("## Per-Category Recall (Junk)")
    lines.append("")
    lines.append("| Category | TP | FN | Recall |")
    lines.append("|----------|----|----|--------|")

    junk_categories = ["scam", "clickbait", "advertorial", "emotional_manipulation", "ai_slop"]
    for cat in junk_categories:
        stats = metrics["category_stats"].get(cat, {"tp": 0, "fn": 0})
        cat_tp = stats["tp"]
        cat_fn = stats["fn"]
        cat_recall = cat_tp / (cat_tp + cat_fn) if (cat_tp + cat_fn) > 0 else 0.0
        lines.append(f"| {cat} | {cat_tp} | {cat_fn} | {cat_recall:.4f} |")

    lines.append("")
    lines.append("## Per-Category False Positive Rate (Quality)")
    lines.append("")
    lines.append("| Category | FP | TN | FP Rate |")
    lines.append("|----------|----|----|---------|")

    quality_categories = ["news", "tech_blog", "educational", "opinion"]
    for cat in quality_categories:
        stats = metrics["category_stats"].get(cat, {"fp": 0, "tn": 0})
        cat_fp = stats["fp"]
        cat_tn = stats["tn"]
        total = cat_fp + cat_tn
        fp_rate = cat_fp / total if total > 0 else 0.0
        lines.append(f"| {cat} | {cat_fp} | {cat_tn} | {fp_rate:.4f} |")

    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    """Run benchmark."""
    parser = argparse.ArgumentParser(description="Run junk-detector benchmark")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full benchmark including LLM scoring",
    )
    args = parser.parse_args()

    # Load dataset
    dataset_path = Path(__file__).parent / "dataset" / "labeled_500.jsonl"
    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path}")
        sys.exit(1)

    samples = load_dataset(dataset_path)
    print(f"Loaded {len(samples)} samples")

    # Run rules-only benchmark
    metrics = calculate_metrics(samples)
    print_results(metrics)

    # Write results
    results_path = Path(__file__).parent / "results.md"
    write_results_md(metrics, results_path)
    print(f"Results written to {results_path}")

    # Handle --full flag
    if args.full:
        print()
        print("LLM mode requires API key, skipping")


if __name__ == "__main__":
    main()
