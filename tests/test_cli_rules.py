"""Tests for the CLI 'rules' command."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from src.cli.main import app

runner = CliRunner()


def test_rules_list_shows_builtin_counts() -> None:
    """Test that --list shows built-in rule counts."""
    result = runner.invoke(app, ["rules", "--list"])
    assert result.exit_code == 0
    assert "Built-in Rules" in result.output
    assert "Scam keywords:" in result.output
    assert "Anxiety phrases:" in result.output
    assert "Advertorial keywords:" in result.output
    assert "AI hedging phrases:" in result.output
    assert "Combo rules:" in result.output
    assert "Custom Rules" in result.output


def test_rules_list_shows_custom_rules(tmp_path: Path, monkeypatch) -> None:
    """Test that --list shows custom rules when a rules file exists."""
    monkeypatch.chdir(tmp_path)
    rules_file = tmp_path / ".junk-rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: my_custom_rule
    keywords:
      - "test"
    target_dimension: scam_prob
    score_contribution: 25
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["rules", "--list"])
    assert result.exit_code == 0
    assert "my_custom_rule" in result.output
    assert "scam_prob" in result.output


def test_rules_init_creates_template(tmp_path: Path, monkeypatch) -> None:
    """Test that --init creates a .junk-rules.yaml template file."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["rules", "--init"])
    assert result.exit_code == 0

    template_file = tmp_path / ".junk-rules.yaml"
    assert template_file.exists()
    content = template_file.read_text(encoding="utf-8")
    assert "rules:" in content
    assert "target_dimension" in content


def test_rules_init_refuses_overwrite(tmp_path: Path, monkeypatch) -> None:
    """Test that --init refuses to overwrite existing file."""
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / ".junk-rules.yaml"
    existing.write_text("existing content", encoding="utf-8")

    result = runner.invoke(app, ["rules", "--init"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_rules_validate_valid_file(tmp_path: Path) -> None:
    """Test that --validate reports valid file."""
    rules_file = tmp_path / "test_rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: valid_rule
    keywords:
      - "keyword"
    target_dimension: advertorial_prob
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["rules", "--validate", str(rules_file)])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_rules_validate_invalid_file(tmp_path: Path) -> None:
    """Test that --validate reports errors for invalid file."""
    rules_file = tmp_path / "bad_rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: bad_rule
    keywords:
      - "keyword"
    target_dimension: nonexistent_dimension
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["rules", "--validate", str(rules_file)])
    assert result.exit_code == 1
    assert "INVALID" in result.output


def test_rules_validate_missing_file() -> None:
    """Test that --validate handles missing file."""
    result = runner.invoke(app, ["rules", "--validate", "/nonexistent/rules.yaml"])
    assert result.exit_code == 1
    assert "INVALID" in result.output


def test_rules_no_flag_shows_hint() -> None:
    """Test that running 'rules' without flags shows usage hint."""
    result = runner.invoke(app, ["rules"])
    assert result.exit_code == 0
    assert "--list" in result.output or "--init" in result.output or "--validate" in result.output
