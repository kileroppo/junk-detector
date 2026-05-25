# PRD: Junk Detector 重生计划 — 从"万物"回归"一"

**Label**: `ready-for-agent`
**Created**: 2026-05-25
**Origin**: 道德经（道）× 孙子兵法（术）深度审计后的战略重构

---

## Problem Statement

Junk Detector 当前有 8700 行代码、65 个 Python 文件、3 套评分编排系统、但**零测试、零验证、多处 Bug、大量死代码**。项目的核心价值（LLM 内容质量判断）被过度工程淹没，无法证明自己比"直接问 ChatGPT"更好。需要一次系统性的**减法重构 + 核心加固**，让项目回归到"一个人能稳定使用的防骗雷达"状态。

---

## Solution

执行"为道日损"策略：删除 ~40% 死代码和冗余系统，修复关键 Bug，建立最小测试保障，聚焦提升核心差异化能力（自动化 + 记忆 + 成本控制），最终达到"开发者自己每天用 CLI 评 5 篇文章且结果可信"的验收标准。

---

## User Stories

1. As a developer/user, I want the project to have zero dead code, so that every file I read are actually being used and maintained.
2. As a developer, I want at least 10 core tests covering the scoring pipeline, so that I can refactor without fear of silent regression.
3. As a user, I want the LLM call to have a 30-second timeout, so that a hung API doesn't freeze my CLI or block my server indefinitely.
4. As a user, I want input text to be capped at 50,000 characters, so that I don't accidentally spend $10 on one API call.
5. As a user, I want the cost to be correctly reported after a fallback model call, so that I know my actual spending.
6. As a user, I want recently scored URLs to return the cached result (not a 429 error), so that I can re-check a score without waiting 60 seconds.
7. As a user, I want `junk-detector score --url` to work reliably on real Chinese tech blog URLs, so that I can trust the extraction and scoring.
8. As a developer, I want async functions to not block the event loop with synchronous SQLite calls, so that the API server can handle concurrent requests.
9. As a user, I want `config.yaml` to be read and parsed once at startup (cached), so that each scoring request is faster.
10. As a user, I want my user preferences (custom weights, model) to actually affect the scoring when I call the API authenticated, so that personalization works.
11. As a developer, I want a single scoring orchestration path (not 3 parallel systems), so that the codebase is understandable and maintainable.
12. As a user, I want the health check endpoint to verify LLM API connectivity, so that "healthy" actually means the service can score content.
13. As a user, I want the rules engine to have 200+ keywords (not 30), so that more obvious junk is caught without spending LLM tokens.
14. As a user, I want the prompt to focus on fewer dimensions (5 instead of 9) for initial screening, so that results are more accurate and tokens are saved.
15. As a developer, I want a `.env.example` file with all required/optional env vars documented, so that new setup is not a guessing game.
16. As a user, I want a 7-day result cache for URLs, so that monitoring the same RSS feed doesn't re-score unchanged articles.
17. As a developer, I want the project to start up and fail-fast if `DEEPSEEK_API_KEY` is missing, so that I don't get a cryptic error mid-scoring.
18. As a user, I want `junk-detector monitor start` to produce a daily summary of what it scored, so that I have a reason to run it.
19. As a developer, I want the source reputation hydrator to use a SQL WHERE clause instead of loading 1000 rows and filtering in Python, so that it's efficient.
20. As a user, I want basic prompt injection defense (output validation), so that adversarial input doesn't produce fake 100/100 scores.

---

## Implementation Decisions

### Phase 1: 损 — 删除死代码（Day 1 上午）

- **Delete `src/core/plans/` directory entirely** — third scoring orchestration system, never imported anywhere.
- **Delete `src/dispatcher/dispatcher.py`** — 200-line Dispatcher class that MonitorService doesn't use. Keep `models.py`, `retry.py`, `task_queue.py` (used by MonitorService).
- **Delete `src/extractors/multimodal.py`** — VLM image analysis requiring GPT-4o vision, unused in practice.
- **Delete `src/core/embeddings.py` `find_similar()` function** — O(n) brute-force similarity with Ollama dependency. Keep `embed_content()` and `cosine_similarity()` as utility only.
- **Remove `train_from_history()` from `fast_classifier.py`** — ML training code with no data. Keep the rule-based `_rule_based_classify()`.
- **Remove `summarizer.py`** — duplicate of `_summarize_text()` in `pipeline_stages.py`. Keep only one implementation.
- **Strip `hydrate_similar_articles()` from hydrators** — depends on deleted embedding similarity search.

### Phase 2: 修 — Bug 修复（Day 1 下午）

- **Fix cost accumulation bug** in `scorer.py`: change `result.cost += result.cost` to track primary cost separately and add both.
- **Add `max_length=50000` to `ScoreRequest.text`** in `api/app.py`.
- **Add `timeout=30.0` to LiteLLM calls** in `llm_judge.py` via kwargs.
- **Wrap synchronous SQLite calls in `asyncio.to_thread()`** for all functions called from async context: `hydrate_source_reputation`, `hydrate_article_stats`, `_save_result`, `save_fingerprint`.
- **Change dedup behavior**: instead of raising 429, return the previously cached ScoreResult from the database (query by content_hash).
- **Fix `model_copy()` to use `deep=True`** in scorer.py to prevent config dict mutation.
- **Wire user preferences into `/score` endpoint**: call `PreferencesService.build_scoring_config(user_id)` when user is authenticated.
- **Add startup validation**: in `app.py` lifespan event, check that at least one LLM API key is configured.

### Phase 3: 固 — 测试保障（Day 2）

- Create `tests/test_rules.py` — test each rule category (scam, emotional, advertorial, AI) against known-good and known-bad inputs.
- Create `tests/test_scorer.py` — mock `litellm.acompletion`, verify the orchestration logic (rules override, fallback trigger, label generation, weight calculation).
- Create `tests/test_api.py` — FastAPI TestClient, verify /score, /history, /health endpoints, error handling.
- Create `tests/test_dedup.py` — verify TTLCache behavior, should_score logic.
- Create `tests/test_extract.py` — mock httpx responses, verify web extraction logic for article/main/body fallbacks.
- Create `tests/test_content_filter.py` — verify pre-filter catches violation categories.
- Create `tests/test_pipeline.py` — mock stages, verify pipeline halts on critical failure, continues on non-critical.
- Create `tests/test_config.py` — verify config loading, model preset resolution, env var overrides.
- Create `tests/test_fingerprint.py` — verify simhash, hamming distance, save/load.
- Create `tests/test_rate_limit.py` — verify sliding window behavior, skip paths, per-user limits.

### Phase 4: 强 — 核心能力增强（Day 3-5）

- **Expand rules engine** from ~30 to 200+ keywords:
  - Scam: add cryptocurrency scam patterns, fake investment, MLM keywords
  - Emotional: add more anxiety patterns, FOMO phrases, clickbait templates
  - Advertorial: add affiliate marketing patterns, influencer promotion signals
  - Source: add more recognizable spam domain patterns
- **Add result caching by content_hash with 7-day TTL**: before calling LLM, check if content_hash exists in DB with scored_at within 7 days; if yes, return stored result immediately.
- **Optimize source reputation**: replace Python-side filtering with SQL `WHERE source_url LIKE ?` query indexed by domain.
- **Cache config.yaml**: load once at module import time, expose `reload_config()` for explicit refresh.
- **Add output validation**: after LLM returns, sanity-check (e.g., if ALL dimensions are 100 and confidence is 1.0, flag as suspicious and return low-confidence default).
- **Create `.env.example`** documenting all env vars.
- **Improve health check**: `/health` pings LLM API with a minimal request to verify connectivity.

### Phase 5: 用 — 实际使用验证（Day 5-12）

- Developer uses `junk-detector score --url` daily on 5 real articles
- Track in a simple markdown log: URL, expected quality, actual score, agreement (Y/N)
- After 7 days: compute agreement rate. If < 70%, iterate on prompt. If >= 70%, declare v0.2 stable.
- Based on daily usage, add any missing rule keywords that would have caught junk articles without LLM.

### Architecture: Single Scoring Path

After Phase 1, the call graph becomes:

```
CLI / API / MonitorService
         │
         ▼
    scorer.score()          ← 唯一的编排入口
    ├── content_filter.check_content()    (违规预过滤)
    ├── fast_classifier.classify_fast()   (规则快筛, log only)
    ├── rules.apply_rules()              (维度覆盖)
    ├── llm_judge.judge()                (LLM 调用)
    ├── _calculate_overall()             (加权计算)
    └── _generate_labels()               (标签生成)
```

`pipeline.py` + `pipeline_stages.py` 保留但简化为**仅 MonitorService 使用的薄包装**（extract → score → save），不再有 enrich/preprocess/postprocess 的复杂 hydrator 链。

### Schema Change

- Add `user_id INTEGER` column to `scores` table (nullable, for future multi-tenant)
- Add index on `source_url` for reputation queries
- Add `cached_at TEXT` column for result cache TTL tracking

### Module Responsibility After Refactor

| Module | Responsibility | Deep/Shallow |
|--------|---------------|--------------|
| `scorer.py` | 唯一评分编排入口 | Deep — 简单接口，复杂内部 |
| `rules.py` | 确定性规则引擎 | Deep — 扩充后覆盖面大 |
| `llm_judge.py` | LLM 调用 + 响应解析 | Medium |
| `content_filter.py` | 违规预过滤 | Shallow but correct |
| `storage/db.py` | 持久化 + 查询 + 缓存 | Deep |
| `extractors/web.py` | 网页提取 | Medium |
| `thunder/monitor.py` | RSS 轮询 + 去重 | Medium |
| `monitor/service.py` | 集成编排 | Thin orchestrator |

---

## Testing Decisions

### What makes a good test here

- **Test external behavior, not implementation**: verify that `apply_rules("日入过万 躺赚 财富自由")` returns `scam_prob >= 90`, not that it calls `_check_scam_keywords` internally.
- **Mock external dependencies**: LiteLLM calls, httpx network calls, file system (config.yaml).
- **Use parametrize** for rule engine tests — one test function, 20+ input/expected pairs.
- **Async tests** use `pytest-asyncio` with `asyncio_mode = "auto"` (already configured in pyproject.toml).

### Modules to test (priority order)

1. `rules.py` — deterministic, easily testable, high ROI
2. `scorer.py` — core orchestration, mock LLM
3. `api/app.py` — integration via FastAPI TestClient
4. `dedup.py` — stateful logic, needs edge case coverage
5. `extractors/web.py` — mock HTTP responses
6. `content_filter.py` — same pattern as rules
7. `pipeline.py` — verify stage ordering and error handling
8. `config.py` — config resolution logic
9. `content_fingerprint.py` — pure algorithm, easy to test
10. `rate_limit.py` — time-dependent, mock `time.time()`

### Test infrastructure

- No test infrastructure exists yet (`tests/__init__.py` only)
- Use `conftest.py` for shared fixtures: mock LLM response, sample texts (known junk, known good), temp DB path
- No need for integration tests with real LLM (too slow, costs money) — use recorded responses

---

## Out of Scope

- **Multi-tenant SaaS features** — no billing, no team management, no user isolation beyond basic user_id tracking
- **Docker / deployment** — local development only for now
- **Webhook endpoint integration** — no external systems will push to this tool
- **English rules engine** — primary use case is Chinese content
- **ML model training** — insufficient data, defer until 500+ scored articles
- **Multimodal/VLM analysis** — text-only scoring is sufficient
- **Mobile app / browser extension** — CLI + API is enough
- **Real-time collaboration** — single user tool
- **Internationalization beyond zh/en prompts** — two languages are enough
- **Performance optimization for > 10,000 articles** — personal use won't hit this scale in 2026

---

## Further Notes

### Success Criteria

| Metric | Target | How to Measure |
|--------|--------|---------------|
| Dead code removed | >= 800 lines deleted | `git diff --stat` |
| Test coverage (core modules) | 10+ test files, 50+ test cases | `pytest --co -q \| wc -l` |
| Known bugs fixed | 6/6 listed bugs resolved | Manual verification |
| Daily usage agreement rate | >= 70% (score matches human judgment) | 7-day usage log |
| Average scoring latency | < 8 seconds (text input) | CLI timing |
| Cost per scoring | < ¥0.05 (DeepSeek) | LiteLLM cost tracking |
| Rules skip rate | >= 15% of obvious junk caught by rules alone | Stats from usage log |

### Philosophical Anchors (for decision-making during implementation)

- **道德经·第二十二章「少则得，多则惑」** — When in doubt, delete rather than add.
- **孙子·虚实篇「避实击虚」** — Don't optimize what doesn't matter (multi-tenant, Docker). Invest in what does (prompt accuracy, rule coverage, caching).
- **道德经·第四十八章「为道日损」** — Each PR should make the codebase smaller OR more tested. Never just bigger.
- **孙子·作战篇「兵贵神速」** — Ship Phase 1+2 in one PR. Don't over-plan Phase 4+5 until Phase 3 proves the foundation is solid.

### Execution Order (strict dependency)

```
Phase 1 (删) ──→ Phase 2 (修) ──→ Phase 3 (测) ──→ Phase 4 (强) ──→ Phase 5 (用)
   │                │                │                │                │
   │ 1 PR           │ 1 PR           │ 1 PR           │ 2-3 PRs        │ no PR
   │ "prune"        │ "fix-bugs"     │ "add-tests"    │ "strengthen"    │ (usage log)
   ▼                ▼                ▼                ▼                ▼
 不能跳过          依赖 Phase 1     依赖 Phase 2    测试保护下安全改    验证一切
```

### Risk Register

| Risk | Probability | Mitigation |
|------|------------|------------|
| 删除代码时误删有用代码 | Medium | Git branch, 可回退; 删前 grep 确认无 import |
| Prompt 改完后评分质量下降 | Medium | Phase 5 每日对照记录; 保留原 prompt 作为 fallback |
| 规则扩充后误杀正常内容 | Low | 每条规则加 confidence < 0.9，不直接覆盖 LLM |
| SQLite 性能不够 | Very Low | 个人使用，< 10K 行，不会是问题 |
