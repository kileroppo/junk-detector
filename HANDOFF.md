# Handoff — Junk Detector

## What was built (this session)

| PR/Commit | Content |
|-----------|---------|
| [#5](https://github.com/kileroppo/junk-detector/pull/5) | Thunder real-time stream monitoring + Dispatcher task scheduling |
| [#7](https://github.com/kileroppo/junk-detector/pull/7) | Web UI (Jinja2+HTMX+Tailwind) + Playwright SPA extraction + User auth (JWT+API Key) + User preferences |
| [#8](https://github.com/kileroppo/junk-detector/pull/8) | API rate limiting (sliding window) + English prompt support |
| `ef184f6` | Fix: replaced `python-jose` with `PyJWT` for Python 3.12 compatibility |
| `d2e34d5` | Comprehensive README with all features and usage examples |

All merged to `main` and pushed.

## Current state

**Functionally complete** — all features work. One environment issue on user's machine:

- **Bug**: User's `.venv` pip is incorrectly linked to Miniforge3 global env, causing `pip install` to install packages to the wrong location. **Resolution**: user needs to recreate `.venv` (`rm -rf .venv && python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .`).

### Working features (all on main)

- CLI: `score --text/--url/--file`, `history`, `serve`, `monitor start/stats/add-source`
- API: `POST /score`, `GET /history`, `GET /health`, auth endpoints, preferences endpoints
- Web UI: `/dashboard`, `/score-form`, `/history-page`, `/monitor-status`
- 9-dimension scoring with 4 AI providers (Ollama/DeepSeek/OpenAI/Anthropic)
- Deterministic rules engine + content violation pre-filter
- Source reputation (blacklist/whitelist/auto-blacklist)
- Platform-specific weight profiles (WeChat/小红书/知乎/blog)
- Content embedding + similarity detection
- Long article summarization
- 5-stage composable pipeline (extract → enrich → preprocess → score → postprocess)
- Thunder: RSS/Webhook real-time monitoring with deduplication
- Dispatcher: priority queue + max_in_flight concurrency + exponential backoff retry
- Playwright SPA extraction (optional `[browser]` dependency)
- User auth: JWT (24h) + API Key + bcrypt
- User preferences: per-user weights/thresholds/model/sources
- API rate limiting: sliding window, per-user + global
- Multi-language prompts: zh/en with auto-switch by user preference
- SQLite storage for scores + users + preferences

## Known issues

1. **User's local `.venv` broken** — pip installs to Miniforge3 instead of venv (needs venv recreate)
2. **No multi-tenant data isolation** — `scores` table doesn't have `user_id` column yet
3. **Web UI monitor page** — shows placeholder stats when monitor service isn't running as part of the API server
4. **`passlib` bcrypt warning** — `bcrypt.__about__` attribute error on newer bcrypt versions (cosmetic, doesn't break functionality)

## Key artifacts (don't duplicate)

- README with full usage: `README.md`
- Config reference: `config.yaml`
- Issues breakdown: `ISSUES.md`
- Chinese prompt: `prompts/score_content.txt`
- English prompt: `prompts/score_content_en.txt`

## What to do next (by priority)

1. **Fix multi-tenant** — add `user_id` to scores table, filter history by authenticated user
2. **Docker deployment** — Dockerfile + docker-compose for easy deployment
3. **Webhook endpoint integration** — wire the webhook source into the FastAPI app so `POST /webhook/content` actually works end-to-end
4. **More RSS sources** — add curated Chinese tech/news feeds as defaults
5. **Notification system** — send alerts (email/企业微信/Slack) when monitored content scores below threshold

## Suggested skills for next session

| Scenario | Skill |
|----------|-------|
| Fixing multi-tenant isolation | `tdd` |
| Docker deployment setup | `prototype` |
| Planning notification system | `to-prd` → `to-issues` |
| Architecture review | `improve-codebase-architecture` |
| Debugging venv/dependency issues | `diagnose` |
| Broad codebase understanding | `zoom-out` |

## Environment notes

- Python 3.11+ required (user has 3.12)
- `.env` file with `DEEPSEEK_API_KEY` for default operation
- `config.yaml` controls model selection, weights, platforms, sources, rate limits
- `pip install -e .` for development install
- `pip install -e ".[browser]"` + `playwright install chromium` for SPA support
- JWT dependency is now `PyJWT` (not `python-jose`) — import as `import jwt as pyjwt`
- Skills at `.kiro/skills/`

## Repo

**GitHub:** https://github.com/kileroppo/junk-detector
**Branch:** `main` (all work merged)
