"""Tests for custom rules loader and validator."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.custom_rules import (
    CustomRule,
    apply_custom_rules,
    clear_rules_cache,
    generate_template,
    load_custom_rules,
    validate_rules_file,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear rules cache before and after each test for isolation."""
    clear_rules_cache()
    yield
    clear_rules_cache()


def test_load_custom_rules_valid_yaml(tmp_path: Path) -> None:
    """Test loading valid custom rules from a YAML file."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: test_rule
    keywords:
      - "scam"
      - "fraud"
    target_dimension: scam_prob
    score_contribution: 30
    confidence: 0.8
    min_keyword_hits: 1
""",
        encoding="utf-8",
    )

    rules = load_custom_rules(path=rules_file)
    assert len(rules) == 1
    assert rules[0].name == "test_rule"
    assert rules[0].keywords == ["scam", "fraud"]
    assert rules[0].target_dimension == "scam_prob"
    assert rules[0].score_contribution == 30.0
    assert rules[0].confidence == 0.8


def test_load_custom_rules_missing_file() -> None:
    """Test that missing file returns empty list."""
    rules = load_custom_rules(path=Path("/nonexistent/path/rules.yaml"))
    assert rules == []


def test_load_custom_rules_invalid_yaml(tmp_path: Path) -> None:
    """Test that invalid YAML returns empty list gracefully."""
    rules_file = tmp_path / "bad.yaml"
    rules_file.write_text("{{invalid yaml: [", encoding="utf-8")

    rules = load_custom_rules(path=rules_file)
    assert rules == []


def test_load_custom_rules_no_rules_key(tmp_path: Path) -> None:
    """Test that YAML without 'rules' key returns empty list."""
    rules_file = tmp_path / "norules.yaml"
    rules_file.write_text("something_else:\n  - foo\n", encoding="utf-8")

    rules = load_custom_rules(path=rules_file)
    assert rules == []


def test_load_custom_rules_skips_invalid_entries(tmp_path: Path) -> None:
    """Test that invalid rule entries are skipped while valid ones load."""
    rules_file = tmp_path / "mixed.yaml"
    rules_file.write_text(
        """
rules:
  - name: valid_rule
    keywords:
      - "test"
    target_dimension: scam_prob
  - name: invalid_rule
    keywords:
      - "test"
    target_dimension: invalid_dimension
""",
        encoding="utf-8",
    )

    rules = load_custom_rules(path=rules_file)
    assert len(rules) == 1
    assert rules[0].name == "valid_rule"


def test_apply_custom_rules_keyword_match() -> None:
    """Test applying custom rules detects keywords and applies scores."""
    rules = [
        CustomRule(
            name="crypto_scam",
            keywords=["bitcoin", "guaranteed returns"],
            target_dimension="scam_prob",
            score_contribution=30,
            confidence=0.85,
            min_keyword_hits=1,
        )
    ]

    content = "Invest in bitcoin for guaranteed returns!"
    result = apply_custom_rules(content, rules)

    assert "custom_crypto_scam" in result.matched_rules
    assert result.dimension_overrides["scam_prob"] == 30.0
    assert result.confidence["scam_prob"] == 0.85


def test_apply_custom_rules_no_match() -> None:
    """Test that rules do not fire when keywords are absent."""
    rules = [
        CustomRule(
            name="crypto_scam",
            keywords=["bitcoin", "guaranteed returns"],
            target_dimension="scam_prob",
            score_contribution=30,
            confidence=0.85,
            min_keyword_hits=1,
        )
    ]

    content = "This is a normal article about cooking."
    result = apply_custom_rules(content, rules)

    assert result.matched_rules == []
    assert result.dimension_overrides == {}


def test_apply_custom_rules_regex_patterns() -> None:
    """Test that regex patterns are correctly matched."""
    rules = [
        CustomRule(
            name="phone_scam",
            keywords=[],
            patterns=[r"\d{3}-\d{4}-\d{4}", r"call now"],
            target_dimension="scam_prob",
            score_contribution=25,
            confidence=0.75,
            min_keyword_hits=1,
        )
    ]

    content = "Call now at 123-4567-8901 for free consultation!"
    result = apply_custom_rules(content, rules)

    assert "custom_phone_scam" in result.matched_rules
    assert result.dimension_overrides["scam_prob"] == 25.0


def test_apply_custom_rules_min_keyword_hits() -> None:
    """Test that min_keyword_hits threshold is enforced."""
    rules = [
        CustomRule(
            name="multi_trigger",
            keywords=["word1", "word2", "word3"],
            target_dimension="advertorial_prob",
            score_contribution=20,
            confidence=0.7,
            min_keyword_hits=2,
        )
    ]

    # Only 1 hit - should not trigger
    content_one_hit = "This contains word1 only."
    result = apply_custom_rules(content_one_hit, rules)
    assert result.matched_rules == []

    # 2 hits - should trigger
    content_two_hits = "This contains word1 and word2."
    result = apply_custom_rules(content_two_hits, rules)
    assert "custom_multi_trigger" in result.matched_rules


def test_apply_custom_rules_score_capped_at_100() -> None:
    """Test that score contributions are capped at 100."""
    rules = [
        CustomRule(
            name="rule1",
            keywords=["trigger"],
            target_dimension="scam_prob",
            score_contribution=60,
            confidence=0.8,
            min_keyword_hits=1,
        ),
        CustomRule(
            name="rule2",
            keywords=["trigger"],
            target_dimension="scam_prob",
            score_contribution=60,
            confidence=0.9,
            min_keyword_hits=1,
        ),
    ]

    content = "trigger word here"
    result = apply_custom_rules(content, rules)

    assert result.dimension_overrides["scam_prob"] == 100.0
    assert result.confidence["scam_prob"] == 0.9  # max of the two


def test_apply_custom_rules_invalid_regex_handled() -> None:
    """Test that invalid regex patterns are skipped gracefully."""
    rules = [
        CustomRule(
            name="bad_regex",
            keywords=["fallback"],
            patterns=["[invalid(regex"],
            target_dimension="scam_prob",
            score_contribution=20,
            confidence=0.7,
            min_keyword_hits=1,
        )
    ]

    content = "This has fallback keyword."
    result = apply_custom_rules(content, rules)

    # Should still fire due to keyword match
    assert "custom_bad_regex" in result.matched_rules


def test_validate_rules_file_valid(tmp_path: Path) -> None:
    """Test validation of a valid rules file."""
    rules_file = tmp_path / "valid.yaml"
    rules_file.write_text(
        """
rules:
  - name: test
    keywords:
      - "keyword"
    target_dimension: scam_prob
    score_contribution: 20
""",
        encoding="utf-8",
    )

    is_valid, errors = validate_rules_file(str(rules_file))
    assert is_valid is True
    assert errors == []


def test_validate_rules_file_invalid_dimension(tmp_path: Path) -> None:
    """Test validation catches invalid target_dimension."""
    rules_file = tmp_path / "invalid.yaml"
    rules_file.write_text(
        """
rules:
  - name: bad_dimension
    keywords:
      - "keyword"
    target_dimension: invalid_dimension
""",
        encoding="utf-8",
    )

    is_valid, errors = validate_rules_file(str(rules_file))
    assert is_valid is False
    assert len(errors) == 1
    assert "Rule 1" in errors[0]


def test_validate_rules_file_missing_fields(tmp_path: Path) -> None:
    """Test validation catches missing required fields."""
    rules_file = tmp_path / "missing.yaml"
    rules_file.write_text(
        """
rules:
  - keywords:
      - "keyword"
""",
        encoding="utf-8",
    )

    is_valid, errors = validate_rules_file(str(rules_file))
    assert is_valid is False
    assert len(errors) >= 1


def test_validate_rules_file_not_found() -> None:
    """Test validation handles missing file."""
    is_valid, errors = validate_rules_file("/nonexistent/path/rules.yaml")
    assert is_valid is False
    assert "File not found" in errors[0]


def test_validate_rules_file_bad_yaml(tmp_path: Path) -> None:
    """Test validation handles malformed YAML."""
    rules_file = tmp_path / "bad.yaml"
    rules_file.write_text("{{invalid: [yaml", encoding="utf-8")

    is_valid, errors = validate_rules_file(str(rules_file))
    assert is_valid is False
    assert "YAML parse error" in errors[0]


def test_validate_rules_file_missing_rules_key(tmp_path: Path) -> None:
    """Test validation catches missing 'rules' key."""
    rules_file = tmp_path / "nokey.yaml"
    rules_file.write_text("other_key: value\n", encoding="utf-8")

    is_valid, errors = validate_rules_file(str(rules_file))
    assert is_valid is False
    assert "Missing 'rules' key" in errors[0]


def test_generate_template_valid_yaml() -> None:
    """Test that generated template is valid YAML and contains expected structure."""
    template = generate_template()
    data = yaml.safe_load(template)

    assert isinstance(data, dict)
    assert "rules" in data
    assert isinstance(data["rules"], list)
    assert len(data["rules"]) >= 1

    # Verify the template rules are valid CustomRule schemas
    for item in data["rules"]:
        rule = CustomRule(**item)
        assert rule.name
        assert rule.target_dimension in {
            "scam_prob",
            "advertorial_prob",
            "emotional_manipulation",
            "ai_generated_prob",
        }


def test_load_custom_rules_auto_discovery_returns_empty_when_no_file(
    tmp_path: Path, monkeypatch
) -> None:
    """Test auto-discovery returns empty list when no rules file exists."""
    monkeypatch.chdir(tmp_path)
    rules = load_custom_rules()
    assert rules == []


def test_load_custom_rules_caching(tmp_path: Path) -> None:
    """Test that loading the same unchanged file uses cached result."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: cached_rule
    keywords:
      - "test"
    target_dimension: scam_prob
""",
        encoding="utf-8",
    )

    # First load - should parse
    rules1 = load_custom_rules(path=rules_file)
    assert len(rules1) == 1
    assert rules1[0].name == "cached_rule"

    # Second load - should return cached (same object)
    rules2 = load_custom_rules(path=rules_file)
    assert rules2 is rules1

    # After clearing cache, should re-parse
    clear_rules_cache()
    rules3 = load_custom_rules(path=rules_file)
    assert len(rules3) == 1
    assert rules3 is not rules1


def test_load_custom_rules_cache_invalidated_on_mtime_change(tmp_path: Path) -> None:
    """Test that cache is invalidated when file mtime changes."""
    import os
    import time

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: original_rule
    keywords:
      - "original"
    target_dimension: scam_prob
""",
        encoding="utf-8",
    )

    rules1 = load_custom_rules(path=rules_file)
    assert len(rules1) == 1
    assert rules1[0].name == "original_rule"

    # Modify the file with a different mtime
    time.sleep(0.05)
    rules_file.write_text(
        """
rules:
  - name: updated_rule
    keywords:
      - "updated"
    target_dimension: advertorial_prob
""",
        encoding="utf-8",
    )
    # Ensure mtime is different
    os.utime(rules_file, (time.time() + 1, time.time() + 1))

    rules2 = load_custom_rules(path=rules_file)
    assert len(rules2) == 1
    assert rules2[0].name == "updated_rule"


def test_load_custom_rules_logs_warning_on_invalid_yaml(tmp_path: Path, caplog) -> None:
    """Test that invalid YAML produces a warning log message."""
    import logging

    rules_file = tmp_path / "bad.yaml"
    rules_file.write_text("{{invalid yaml: [", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="src.core.custom_rules"):
        rules = load_custom_rules(path=rules_file)

    assert rules == []
    assert "Failed to parse custom rules file" in caplog.text


def test_load_custom_rules_logs_warning_on_invalid_rule_entry(tmp_path: Path, caplog) -> None:
    """Test that invalid rule entries produce warning log messages."""
    import logging

    rules_file = tmp_path / "mixed.yaml"
    rules_file.write_text(
        """
rules:
  - name: valid_rule
    keywords:
      - "test"
    target_dimension: scam_prob
  - name: invalid_rule
    keywords:
      - "test"
    target_dimension: invalid_dimension
""",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="src.core.custom_rules"):
        rules = load_custom_rules(path=rules_file)

    assert len(rules) == 1
    assert "Skipping invalid custom rule at index 1" in caplog.text
