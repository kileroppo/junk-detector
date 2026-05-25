# Junk Detector

AI-powered content quality scorer for detecting scam, clickbait, and junk content in Chinese tech media.

## Features

- **9-dimension scoring**: originality, info density, reasoning quality, readability, timeliness, AI-generated probability, emotional manipulation, advertorial probability, scam probability
- **LLM + rules hybrid**: rules layer for fast obvious-junk detection, LLM for nuanced judgment
- **Tiered cost strategy**: rules (free) -> cheap model -> expensive model re-evaluation for low-confidence results
- **Multi-input**: URL (with SPA support), text, file
- **Prompt injection defense**: system/user message separation with content isolation
- **CLI + API + Web UI**: three ways to use

## Installation

```bash
pip install -e .
```

For SPA site support (WeChat articles, Juejin, etc.):

```bash
pip install -e ".[browser]"
playwright install chromium
```

## Quick Usage

```bash
# Fast screening (4 dimensions, cheap)
junk-detector quick --text "日入过万！限时免费！加微信领取！"

# Full 9-dimension scoring
junk-detector score --url "https://example.com/article"

# Batch processing
junk-detector batch --urls-file urls.txt

# Start API server + Web UI
junk-detector serve
```

See [QUICKSTART.md](QUICKSTART.md) for detailed usage guide.

## Architecture

Content flows through a multi-stage pipeline: extraction -> rule-based pre-filtering -> LLM scoring (with system/user message separation for injection defense) -> output validation -> weighted score computation -> label generation -> storage. The system uses a tiered model strategy where rules handle obvious cases for free, a cheap model scores the rest, and an expensive model re-evaluates low-confidence results.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (target: 85%+ coverage)
python -m pytest tests/ -q

# Lint
ruff check src/ tests/
```

## Configuration

Copy `.env.example` to `.env` and add your API key:

```bash
DEEPSEEK_API_KEY=your-key-here
```

See `config.yaml` for full configuration (models, scoring weights, monitoring sources, rate limits).

## License

MIT
