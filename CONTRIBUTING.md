# Contributing to Junk Detector

Thanks for your interest in contributing! This guide covers development setup, testing, and contribution workflows.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/kileroppo/junk-detector.git
cd junk-detector

# Install in development mode
pip install -e ".[dev]"

# Verify installation
junk-detector --help
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -q

# Run with coverage
python -m pytest tests/ --cov=src --cov-fail-under=80

# Run specific test file
python -m pytest tests/test_rules.py -q
```

## Linting

```bash
# Check for lint errors
ruff check src/ tests/

# Auto-fix lint errors
ruff check --fix src/ tests/

# Format check
ruff format --check src/ tests/
```

## Contributing Detection Rules

Rules are the core of junk-detector. You can contribute new keyword lists, regex patterns, or combo rules.

### Rule Format

Custom rules use YAML format. See [docs/rule-format.md](docs/rule-format.md) for the full specification.

```yaml
rules:
  - name: "my-new-rule"
    keywords: ["keyword1", "keyword2"]
    patterns: ["regex\\d+pattern"]
    target_dimension: "scam_prob"
    score_contribution: 15.0
```

### Allowed `target_dimension` Values

- `scam_prob` - Scam/fraud probability
- `emotional` - Emotional manipulation
- `advertorial` - Advertorial/sponsored content probability
- `ai_generated` - AI-generated content probability

### Testing Your Rules

1. Create a rules file with your new rules
2. Validate: `junk-detector rules --validate my-rules.yaml`
3. Test against sample content: `junk-detector quick --text "sample content"`
4. Add test cases in `tests/test_custom_rules.py`

### PR Process for Rules

1. Add rules to the appropriate section in `src/core/rules.py`
2. Add test cases covering both positive and negative matches
3. Run the full test suite to ensure no regressions
4. Describe the content type your rule targets in the PR description

## Contributing Platform Patterns

Platform-specific patterns (WeChat, Xiaohongshu, Douyin, etc.) live in the rules engine. To add support for a new platform:

1. Identify platform-specific keywords and patterns
2. Add a platform rule group in `src/core/rules.py`
3. Add test cases with representative content
4. Document the platform in a guide under `docs/`

## PR Requirements

- All tests must pass (`python -m pytest tests/ -q`)
- No lint errors (`ruff check src/ tests/`)
- Descriptive commit messages with type prefix (`feat:`, `fix:`, `docs:`)
- One logical change per PR
- Update documentation if behavior changes

## Code Style

- Python 3.11+ features welcome
- Follow existing patterns in the codebase
- Use type hints for function signatures
- Keep functions focused and small

## Getting Help

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones
- Use the PR template for contributions
