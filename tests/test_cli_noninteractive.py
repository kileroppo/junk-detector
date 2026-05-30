"""Tests for CLI non-interactive output mode."""
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = str(Path(__file__).parent.parent)


class TestNonInteractiveOutput:
    """Tests that piped output uses plain text markers."""

    def test_quick_piped_output_has_no_ansi(self):
        """When piped, output should not contain ANSI escape sequences."""
        result = subprocess.run(
            [sys.executable, "-m", "src.cli.main", "quick", "--text", "正常的技术文章内容", "--rules-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        # Piped output should not contain ANSI escape codes
        assert "\x1b[" not in result.stdout

    def test_quick_piped_output_uses_brackets(self):
        """Piped output should use [OK]/[WARN]/[DANGER] markers."""
        result = subprocess.run(
            [sys.executable, "-m", "src.cli.main", "quick", "--text", "日入过万 躺赚 加微信", "--rules-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        # Should contain one of the bracket markers
        has_marker = "[OK]" in result.stdout or "[WARN]" in result.stdout or "[DANGER]" in result.stdout
        assert has_marker

    def test_junk_content_shows_danger_or_warn_marker(self):
        """Known junk content should produce [DANGER] or [WARN] in piped output."""
        result = subprocess.run(
            [sys.executable, "-m", "src.cli.main", "quick", "--text",
             "日入过万 躺赚 财富自由 限时免费 加微信领取 名额有限 稳赚不赔",
             "--rules-only"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        assert "[DANGER]" in result.stdout or "[WARN]" in result.stdout
