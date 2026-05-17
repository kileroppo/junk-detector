# Handoff — Junk Detector

## What was built

`junk-detector` — an AI content quality scorer that evaluates articles across 9 dimensions using LLM-as-Judge + deterministic rules. Personal CLI tool now, SaaS-ready architecture.

**Repo:** https://github.com/kileroppo/junk-detector

## Current state

Fully functional MVP + advanced features. All code on `main`, pushed to GitHub.

### Working features

- CLI: `junk-detector score --text/--url/--file`, `history`, `serve`
- API: `POST /score`, `GET /history`, `GET /health`
- 9-dimension scoring with weighted overall score
- 4 AI providers supported: Ollama (local), DeepSeek, OpenAI, Anthropic — switchable via `config.yaml` or `--model` flag
- Deterministic rules engine (scam/emotional/advertorial/AI-generated detection)
- Content violation pre-filter (gambling/porn/violence/drugs/phishing — zero cost)
- Source reputation system (blacklist/whitelist + auto-blacklist)
- Platform-specific weight profiles (WeChat/小红书/知乎/blog)
- Content embedding + similarity detection (洗稿/plagiarism)
- Long article summarization before scoring (saves 60-70% tokens)
- Composable 5-stage pipeline (extract → enrich → preprocess → score → postprocess)
- SQLite history with query/filter support

### Key artifacts (don't duplicate these)

- PRD: `/projects/sandbox/junk-detector-PRD.md`
- Issues breakdown: `junk-detector/ISSUES.md`
- Config: `junk-detector/config.yaml`
- README: `junk-detector/README.md`

## Known limitations

- SPA sites (掘金 juejin.cn) can't be scraped (need Playwright for JS rendering)
- Embedding requires Ollama running locally or OpenAI API key
- No frontend UI yet
- No user auth (SaaS will need this)
- Chinese-only prompt (English articles get scored but prompts are Chinese)

## What to do next (by priority)

1. **Run `setup-matt-pocock-skills`** — configure issue tracker (GitHub), triage labels, domain docs for the project
2. **Create `CONTEXT.md`** — formalize domain language (use `grill-with-docs` skill)
3. **Pick next feature from remaining x-algorithm patterns:**
   - Real-time content stream monitoring (Thunder/Kafka pattern)
   - User preference personalization (Query Hydrator user context)
   - Web UI (simple dashboard showing history + scores)
   - Playwright integration for SPA sites
4. **SaaS preparation:** user auth, multi-tenant, API rate limiting

## Suggested skills for next session

| Scenario | Skill |
|----------|-------|
| Formalizing domain terms | `grill-with-docs` |
| Planning next feature | `grill-me` or `to-prd` |
| Breaking work into tickets | `to-issues` |
| Setting up project tooling | `setup-matt-pocock-skills` |
| Adding new feature with tests | `tdd` |
| Debugging a bug | `diagnose` |
| Architecture improvements | `improve-codebase-architecture` |

## Environment notes

- Python 3.11+ required
- `.env` file with `DEEPSEEK_API_KEY` for default operation
- `config.yaml` controls model selection, weights, platforms, sources
- `pip install -e .` for development install
- Skills installed at `/projects/.kiro/skills/` (14 total)
