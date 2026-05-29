"""Tests for benchmark/compare.py comparison framework."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture
def compare_module():
    """Import benchmark/compare.py as a module."""
    benchmark_dir = Path(__file__).parent.parent / "benchmark"
    sys.path.insert(0, str(benchmark_dir.parent))
    import benchmark.compare as compare
    return compare


def test_compare_module_importable(compare_module) -> None:
    """Test that benchmark/compare.py can be imported."""
    assert hasattr(compare_module, "main")
    assert hasattr(compare_module, "load_dataset")
    assert hasattr(compare_module, "classify_sample")
    assert hasattr(compare_module, "benchmark_rules_engine")
    assert hasattr(compare_module, "generate_comparison_table")


def test_load_dataset(compare_module) -> None:
    """Test that the dataset can be loaded."""
    dataset_path = Path(__file__).parent.parent / "benchmark" / "dataset" / "labeled_500.jsonl"
    if not dataset_path.exists():
        pytest.skip("Dataset not available")

    samples = compare_module.load_dataset(dataset_path)
    assert len(samples) > 0
    # Check sample structure
    sample = samples[0]
    assert "text" in sample
    assert "label" in sample
    assert sample["label"] in ("junk", "quality")


def test_classify_sample(compare_module) -> None:
    """Test that classify_sample returns valid classifications."""
    result = compare_module.classify_sample("正常的技术文章")
    assert result in ("junk", "quality")


def test_classify_sample_scam(compare_module) -> None:
    """Test that obvious scam content is classified as junk."""
    scam_text = "日入过万不是梦！只需一部手机，躺赚被动收入，加微信了解详情。限时免费名额有限"
    result = compare_module.classify_sample(scam_text)
    assert result == "junk"


def test_benchmark_rules_engine(compare_module) -> None:
    """Test benchmark_rules_engine with a small dataset."""
    samples = [
        {"text": "加微信免费赚钱暴富日入过万", "label": "junk", "category": "scam"},
        {"text": "正常的科技新闻报道内容", "label": "quality", "category": "news"},
    ]
    metrics = compare_module.benchmark_rules_engine(samples)

    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1" in metrics
    assert "accuracy" in metrics
    assert "avg_ms_per_sample" in metrics
    assert "total_samples" in metrics
    assert metrics["total_samples"] == 2
    assert 0 <= metrics["precision"] <= 1
    assert 0 <= metrics["recall"] <= 1
    assert 0 <= metrics["f1"] <= 1
    assert metrics["avg_ms_per_sample"] >= 0


def test_generate_comparison_table(compare_module) -> None:
    """Test that comparison table is valid markdown."""
    metrics = {
        "precision": 0.85,
        "recall": 0.75,
        "f1": 0.80,
        "accuracy": 0.80,
        "total_samples": 100,
        "elapsed_seconds": 0.5,
        "avg_ms_per_sample": 5.0,
        "tp": 60,
        "fp": 10,
        "tn": 20,
        "fn": 10,
    }
    md = compare_module.generate_comparison_table(metrics)

    assert "# Junk Detector Comparison Framework" in md
    assert "| Precision |" in md
    assert "| Recall |" in md
    assert "Comparison with Other Approaches" in md
    assert "Pure keyword filters" in md
    assert "ML text classifiers" in md
    assert "LLM-based" in md
    assert "Commercial APIs" in md
    assert "$0" in md


def test_compare_produces_output_file(compare_module, tmp_path: Path, monkeypatch) -> None:
    """Test that running main() produces comparison.md."""
    dataset_path = Path(__file__).parent.parent / "benchmark" / "dataset" / "labeled_500.jsonl"
    if not dataset_path.exists():
        pytest.skip("Dataset not available")

    # Run the comparison
    compare_module.main()

    # Check output file was created
    output_path = Path(__file__).parent.parent / "benchmark" / "comparison.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Junk Detector" in content
    assert "Comparison" in content
