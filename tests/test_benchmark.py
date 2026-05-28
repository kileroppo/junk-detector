"""Tests for the benchmark module."""
import json
from pathlib import Path

import pytest


DATASET_PATH = Path(__file__).parent.parent / "benchmark" / "dataset" / "labeled_500.jsonl"

VALID_LABELS = {"junk", "quality"}
VALID_CATEGORIES = {
    "scam", "clickbait", "advertorial", "emotional_manipulation", "ai_slop",
    "news", "tech_blog", "educational", "opinion",
}
VALID_SOURCE_TYPES = {"wechat", "xiaohongshu", "zhihu", "blog", "douyin"}


def test_dataset_file_exists():
    """Test that the dataset file exists."""
    assert DATASET_PATH.exists(), f"Dataset file not found at {DATASET_PATH}"


def test_dataset_has_500_lines():
    """Test that the dataset file has exactly 500 lines."""
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    assert len(lines) == 500, f"Expected 500 lines, got {len(lines)}"


def test_each_line_is_valid_json_with_required_fields():
    """Test that each line is valid JSON with required fields."""
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                pytest.fail(f"Line {i} is not valid JSON: {line[:100]}")

            assert "text" in entry, f"Line {i} missing 'text' field"
            assert "label" in entry, f"Line {i} missing 'label' field"
            assert "category" in entry, f"Line {i} missing 'category' field"
            assert "source_type" in entry, f"Line {i} missing 'source_type' field"

            assert entry["label"] in VALID_LABELS, (
                f"Line {i} has invalid label: {entry['label']}"
            )
            assert entry["category"] in VALID_CATEGORIES, (
                f"Line {i} has invalid category: {entry['category']}"
            )
            assert entry["source_type"] in VALID_SOURCE_TYPES, (
                f"Line {i} has invalid source_type: {entry['source_type']}"
            )
            assert len(entry["text"]) > 0, f"Line {i} has empty text"


def test_label_distribution():
    """Test that label distribution is correct (250/250)."""
    junk_count = 0
    quality_count = 0

    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry["label"] == "junk":
                junk_count += 1
            elif entry["label"] == "quality":
                quality_count += 1

    assert junk_count == 250, f"Expected 250 junk, got {junk_count}"
    assert quality_count == 250, f"Expected 250 quality, got {quality_count}"


def test_run_benchmark_module_importable():
    """Test that run_benchmark module can be imported."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "benchmark"))
    import run_benchmark  # noqa: F401

    assert hasattr(run_benchmark, "main")
    assert hasattr(run_benchmark, "classify_sample")
    assert hasattr(run_benchmark, "calculate_metrics")
    assert hasattr(run_benchmark, "load_dataset")
