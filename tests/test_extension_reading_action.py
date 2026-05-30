"""Extension reading_action.js alignment tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

EXT_DIR = Path(__file__).parent.parent / "extension"


def test_reading_action_js_exports_enrich():
    script = """
    const fs = require('fs');
    const vm = require('vm');
    const rules = fs.readFileSync('rules.js', 'utf8');
    const ra = fs.readFileSync('reading_action.js', 'utf8');
    const ctx = { module: { exports: {} }, exports: {} };
    vm.runInNewContext(rules, ctx);
    vm.runInNewContext(ra, ctx);
    const text = '1. Skill A\\ngithub.com/a\\n安装: npx skills add\\n2. Skill B\\ngithub.com/b\\n完整指南';
    const padded = (text + '\\n').repeat(20);
    const raw = ctx.scoreContent(padded);
    ctx.enrichScoringResult(raw, padded);
    if (!raw.reading_action || raw.reading_action.key !== 'skim') {
      throw new Error('expected skim action, got ' + JSON.stringify(raw.reading_action));
    }
    if (raw.content_genre !== 'roundup') {
      throw new Error('expected roundup genre, got ' + raw.content_genre);
    }
    """
    subprocess.run(
        ["node", "-e", script],
        cwd=EXT_DIR,
        check=True,
        timeout=10,
    )


def test_manifest_includes_reading_action():
    import json

    manifest = json.loads((EXT_DIR / "manifest.json").read_text())
    scripts = manifest["content_scripts"][0]["js"]
    assert "reading_action.js" in scripts
