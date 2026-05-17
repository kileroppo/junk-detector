# Implementation Issues

Vertical slices for junk-detector, in dependency order.

## Wave 1 — Foundation

### Issue #1: 项目初始化：pyproject.toml + 依赖 + 目录结构

**Blocked by:** None — can start immediately

**What to build:**

Initialize the Python project with proper structure, dependencies, and tooling configuration.

**Acceptance criteria:**

- [ ] `pyproject.toml` with all dependencies declared (fastapi, typer, litellm, httpx, beautifulsoup4, pydantic, markdownify)
- [ ] Directory structure created: `src/{api,cli,core,extractors,models,storage}`, `prompts/`, `tests/`
- [ ] `__init__.py` files in all packages
- [ ] `python -m pip install -e .` succeeds
- [ ] Basic dev tooling configured (ruff for linting)

---

### Issue #2: Pydantic 数据模型：ScoreResult + Content

**Blocked by:** #1

**What to build:**

Define the core data models that flow through the entire system.

**Acceptance criteria:**

- [ ] `ScoreResult` model with: overall_score (0-100), 9 dimension scores, labels list, summary string, confidence, model_used, cost
- [ ] `Content` model with: input_type (url/text/file), text, source_url (optional), title (optional), content_hash
- [ ] `ScoringConfig` model with: weights per dimension, model name, confidence threshold
- [ ] All models have proper validation (score ranges, required fields)
- [ ] Models are importable from `src/models/`

---

## Wave 2 — Core Components (parallel)

### Issue #3: LLM Judge：prompt 模板 + LiteLLM 调用 + 响应解析

**Blocked by:** #2

**What to build:**

The LLM calling layer: format prompts, call LiteLLM, parse structured output into ScoreResult.

**Acceptance criteria:**

- [ ] Prompt template in `prompts/` that instructs LLM to score 9 dimensions with reasoning
- [ ] `llm_judge.py` function: `judge(content: str, config: ScoringConfig) -> ScoreResult`
- [ ] Uses LiteLLM for model-agnostic calling
- [ ] Parses JSON response into ScoreResult (handles malformed responses gracefully)
- [ ] Model name configurable via environment variable or config

---

### Issue #6: 网页抓取 Extractor：URL → 纯文本

**Blocked by:** #2

**What to build:**

Extract clean text content from a URL. Handles common article pages.

**Acceptance criteria:**

- [ ] `web.py` extractor: `extract_from_url(url: str) -> Content`
- [ ] Uses httpx for fetching, BeautifulSoup/markdownify for text extraction
- [ ] Strips nav, footer, ads, scripts — extracts article body
- [ ] Extracts title from `<title>` or `<h1>`
- [ ] Handles common errors (404, timeout, non-HTML) gracefully
- [ ] Returns `Content` model with input_type="url"

---

### Issue #8: 规则层：关键词/模式匹配引擎

**Blocked by:** #2

**What to build:**

Deterministic rule engine that scores specific dimensions based on keyword/pattern matching.

**Acceptance criteria:**

- [ ] `rules.py` with function: `apply_rules(content: str) -> RuleResult`
- [ ] `RuleResult` contains: matched rules list, dimension overrides (e.g. scam_prob=95), confidence per match
- [ ] Scam keywords: "日入过万", "限时免费", "私聊领取", "躺赚", "财富自由" etc.
- [ ] Emotional manipulation patterns: excessive punctuation (!!!、？？？), anxiety phrases
- [ ] Advertorial patterns: product links density, discount codes, "推荐码"
- [ ] Each rule has a name, target dimension, and score contribution

---

### Issue #11: SQLite 存储层：save + query + migration

**Blocked by:** #2

**What to build:**

Storage layer for persisting scoring history.

**Acceptance criteria:**

- [ ] `db.py` with: `save(result: ScoreResult, content: Content)`, `query(filters) -> list`, `get_history(limit) -> list`
- [ ] SQLite schema: id, input_type, source_url, title, content_hash, scored_at, overall_score, dimensions_json, labels_json, summary, model_used, cost, rule_hits
- [ ] Auto-creates DB file on first use
- [ ] Deduplication by content_hash (update if re-scored)
- [ ] Query supports: filter by score range, date range, label

---

## Wave 3 — Integration (parallel)

### Issue #4: Scorer 核心编排：score(text) → ScoreResult

**Blocked by:** #3

**What to build:**

The main scoring orchestrator. Simple interface, complex internals.

**Acceptance criteria:**

- [ ] `scorer.py` with: `score(content: str) -> ScoreResult`
- [ ] Calls LLM Judge and returns parsed result
- [ ] Calculates overall_score from dimension scores using default weights
- [ ] Generates labels based on dimension thresholds (e.g. ai_generated_prob > 70 → "可能AI生成")
- [ ] Generates one-line summary

---

### Issue #5: CLI 入口：`score --text` 命令

**Blocked by:** #4

**What to build:**

Typer CLI that accepts text input and outputs scoring results.

**Acceptance criteria:**

- [ ] `junk-detector score --text "content here..."` outputs formatted JSON result
- [ ] `junk-detector score --file path/to/file.txt` reads file and scores
- [ ] Pretty-printed output with colored scores (green=good, red=bad)
- [ ] `--json` flag for raw JSON output
- [ ] `junk-detector --help` shows usage

---

### Issue #7: CLI 扩展：`score --url` 命令

**Blocked by:** #5, #6

**What to build:**

Extend CLI to accept URL input, extract content, then score.

**Acceptance criteria:**

- [ ] `junk-detector score --url "https://..."` fetches page, extracts text, scores
- [ ] Shows extracted title before scoring
- [ ] Error handling: invalid URL, unreachable page, empty content

---

### Issue #9: 规则层接入 Scorer：规则命中跳过 LLM

**Blocked by:** #4, #8

**What to build:**

Wire rules into the scoring pipeline. High-confidence rule hits skip LLM for those dimensions.

**Acceptance criteria:**

- [ ] Scorer runs rules first, before LLM
- [ ] If rule confidence is high (>=0.9) for a dimension, use rule score directly
- [ ] If ALL dimensions covered by rules with high confidence, skip LLM entirely (cost=0)
- [ ] Mixed case: rules fill some dimensions, LLM fills the rest
- [ ] ScoreResult includes which dimensions came from rules vs LLM

---

### Issue #12: 存储接入：评分后自动存储 + CLI `history` 命令

**Blocked by:** #5, #11

**What to build:**

Wire storage into the scoring flow and add history viewing.

**Acceptance criteria:**

- [ ] Every `score` command automatically saves result to SQLite
- [ ] `junk-detector history` shows recent scores (default last 20)
- [ ] `junk-detector history --min-score 80` filters by score
- [ ] `junk-detector history --label "AI生成"` filters by label
- [ ] Table-formatted output with: date, title/source, overall_score, top labels

---

### Issue #13: FastAPI 接口：POST /score + GET /history

**Blocked by:** #4, #11

**What to build:**

REST API exposing scoring and history functionality.

**Acceptance criteria:**

- [ ] `POST /score` accepts `{"url": "..."}` or `{"text": "..."}`, returns ScoreResult JSON
- [ ] `GET /history` returns paginated history with optional filters (min_score, label, date_from)
- [ ] `GET /health` returns service status
- [ ] Auto-generated OpenAPI docs at `/docs`
- [ ] `junk-detector serve` CLI command starts the API server

---

## Wave 4 — Advanced

### Issue #10: 分级策略：confidence 阈值 + 贵模型复评

**Blocked by:** #9

**What to build:**

Implement tiered model strategy: rules → cheap model → expensive model for low-confidence results.

**Acceptance criteria:**

- [ ] LLM Judge returns confidence score (0-1) alongside dimensions
- [ ] Scorer checks confidence against configurable threshold (default 0.7)
- [ ] Below threshold: re-score with configured high-quality model
- [ ] Config supports: `primary_model`, `fallback_model`, `confidence_threshold`
- [ ] Logging shows which tier was used and total cost

---

## Parallel Execution Guide

```
Wave 1: #1 → #2

Wave 2 (parallel): #3 | #6 | #8 | #11

Wave 3 (parallel): #4→#5→#7 | #9 | #12 | #13

Wave 4: #10
```
