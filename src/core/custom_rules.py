"""Custom rules loader and validator for user-defined detection rules."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from src.core.rules import RuleResult

logger = logging.getLogger(__name__)


class CustomRule(BaseModel):
    """Schema for a user-defined detection rule."""
    name: str = Field(..., description="Rule name (unique identifier)")
    keywords: list[str] = Field(default_factory=list, description="Keywords to match (any triggers)")
    patterns: list[str] = Field(default_factory=list, description="Regex patterns to match")
    target_dimension: str = Field(..., description="Dimension to affect: scam_prob, advertorial_prob, emotional_manipulation, ai_generated_prob")
    score_contribution: float = Field(default=20.0, ge=0, le=100, description="Score to add when rule fires")
    confidence: float = Field(default=0.7, ge=0, le=1.0, description="Confidence level")
    platform: Optional[str] = Field(default=None, description="Optional platform filter")
    min_keyword_hits: int = Field(default=1, ge=1, description="Minimum keyword matches to trigger")

    @field_validator("target_dimension")
    @classmethod
    def validate_dimension(cls, v):
        valid = {"scam_prob", "advertorial_prob", "emotional_manipulation", "ai_generated_prob"}
        if v not in valid:
            raise ValueError(f"target_dimension must be one of: {valid}")
        return v


VALID_DIMENSIONS = {"scam_prob", "advertorial_prob", "emotional_manipulation", "ai_generated_prob"}


def _find_rules_file() -> Optional[Path]:
    """Find custom rules file. Checks in order:
    1. .junk-rules.yaml in cwd
    2. ~/.junk-detector/rules.yaml
    Returns first found, or None.
    """
    # Check local project file
    local = Path.cwd() / ".junk-rules.yaml"
    if local.exists():
        return local

    # Check user home directory
    home = Path.home() / ".junk-detector" / "rules.yaml"
    if home.exists():
        return home

    return None


_rules_cache: dict[str, tuple[float, list[CustomRule]]] = {}


def load_custom_rules(path: Optional[Path] = None) -> list[CustomRule]:
    """Load custom rules from YAML file with mtime-based caching.

    If path is None, auto-discovers from default locations.
    Returns empty list if no file found.
    """
    if path is None:
        path = _find_rules_file()
    if path is None:
        return []

    path_str = str(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []

    # Return cached if file hasn't changed
    if path_str in _rules_cache:
        cached_mtime, cached_rules = _rules_cache[path_str]
        if cached_mtime == mtime:
            return cached_rules

    # Parse and cache
    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except Exception as e:
        logger.warning("Failed to parse custom rules file %s: %s", path, e)
        return []

    if not isinstance(data, dict) or "rules" not in data:
        logger.warning("Custom rules file %s missing 'rules' key", path)
        return []

    rules = []
    for i, item in enumerate(data["rules"]):
        try:
            rule = CustomRule(**item)
            rules.append(rule)
        except Exception as e:
            logger.warning("Skipping invalid custom rule at index %d in %s: %s", i, path, e)
            continue

    _rules_cache[path_str] = (mtime, rules)
    return rules


def clear_rules_cache() -> None:
    """Clear the custom rules cache (useful for testing)."""
    _rules_cache.clear()


def apply_custom_rules(content: str, rules: list[CustomRule]) -> RuleResult:
    """Apply custom rules to content and return results."""
    result = RuleResult()

    for rule in rules:
        # Check keyword matches
        keyword_hits = sum(1 for kw in rule.keywords if kw in content)

        # Check pattern matches
        pattern_hits = 0
        for pattern in rule.patterns:
            try:
                if re.search(pattern, content):
                    pattern_hits += 1
            except re.error:
                continue

        total_hits = keyword_hits + pattern_hits

        if total_hits >= rule.min_keyword_hits:
            result.matched_rules.append(f"custom_{rule.name}")
            current = result.dimension_overrides.get(rule.target_dimension, 0)
            new_score = min(current + rule.score_contribution, 100.0)
            result.dimension_overrides[rule.target_dimension] = new_score
            current_conf = result.confidence.get(rule.target_dimension, 0)
            result.confidence[rule.target_dimension] = max(current_conf, rule.confidence)

    return result


def validate_rules_file(path: str) -> tuple[bool, list[str]]:
    """Validate a custom rules YAML file.

    Returns (is_valid, list_of_errors).
    """
    errors = []
    file_path = Path(path)

    if not file_path.exists():
        return False, [f"File not found: {path}"]

    try:
        content = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return False, [f"YAML parse error: {e}"]
    except Exception as e:
        return False, [f"File read error: {e}"]

    if not isinstance(data, dict):
        return False, ["Root must be a YAML mapping with 'rules' key"]

    if "rules" not in data:
        return False, ["Missing 'rules' key at root level"]

    if not isinstance(data["rules"], list):
        return False, ["'rules' must be a list"]

    for i, item in enumerate(data["rules"]):
        try:
            CustomRule(**item)
        except Exception as e:
            errors.append(f"Rule {i+1}: {e}")

    return len(errors) == 0, errors


def generate_template() -> str:
    """Generate a template custom rules YAML file content."""
    return '''# Junk Detector Custom Rules
# Place this file as .junk-rules.yaml in your project root
# or as ~/.junk-detector/rules.yaml for global rules.
#
# Each rule has:
#   name: unique identifier
#   keywords: list of keywords (any match counts)
#   patterns: list of regex patterns (any match counts)
#   target_dimension: scam_prob | advertorial_prob | emotional_manipulation | ai_generated_prob
#   score_contribution: points to add (0-100, default 20)
#   confidence: confidence level (0-1, default 0.7)
#   platform: optional platform filter (wechat, xiaohongshu, zhihu, douyin)
#   min_keyword_hits: minimum keyword/pattern matches to trigger (default 1)

rules:
  - name: example_crypto_scam
    keywords:
      - "\u7a7a\u6295"
      - "\u8d28\u62bc"
      - "\u5e74\u5316300%"
    target_dimension: scam_prob
    score_contribution: 30
    confidence: 0.8
    min_keyword_hits: 2

  - name: example_fake_review
    keywords:
      - "\u597d\u8bc4\u8fd4\u73b0"
      - "\u4e94\u661f\u597d\u8bc4"
    patterns:
      - "\u52a0\u5fae\u4fe1.*\u8fd4\\\\d+\u5143"
    target_dimension: advertorial_prob
    score_contribution: 25
    confidence: 0.75
'''
