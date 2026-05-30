# 鉴真 API Documentation

Progressive documentation: pick the level that matches your time.

---

## Level 1: Quick Start (5 seconds)

```bash
curl https://api.jianzhen.dev/demo?text=你好
```

Expected response:

```json
{
  "overall_score": 100,
  "verdict": "quality",
  "explanation": "内容质量正常",
  "recommendation": "建议：内容质量正常，可正常阅读"
}
```

---

## Level 2: Core (1 minute)

Three main endpoints cover most use cases:

### GET /demo

Quick rules-only scoring. No authentication required.

```bash
curl "https://api.jianzhen.dev/demo?text=日入过万加微信领取"
```

Returns: `overall_score`, `verdict` (junk/suspicious/quality), `explanation`, `evidence`, `recommendation`.

### POST /score

Full AI-powered scoring (rules + LLM judge). Returns comprehensive 9-dimension analysis.

```bash
curl -X POST https://api.jianzhen.dev/score \
  -H "Content-Type: application/json" \
  -d '{"text": "你的内容"}'
```

Returns: `ScoreResult` with `overall_score`, `dimensions`, `labels`, `summary`, `confidence`.

### GET /health

Service health check. Add `?deep=true` for LLM connectivity verification.

```bash
curl https://api.jianzhen.dev/health
```

Returns: `status`, `version`, `uptime_seconds`, `total_scores`, `rules_loaded`.

---

## Level 3: Full Reference (5 minutes)

### Scoring Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/demo` | GET | No | Rules-only quick score |
| `/score` | POST | Optional | Full AI scoring (rules + LLM) |
| `/score/batch` | POST | Optional | Score multiple items concurrently (max 50) |
| `/score/stream` | POST | Optional | SSE streaming (rules first, then LLM) |
| `/score/batch-upload` | POST | No | Upload CSV/JSONL for background batch scoring |
| `/score/batch-upload/{job_id}` | GET | No | Poll batch job status |

### Info Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Service health (add `?deep=true` for LLM check) |
| `/usage` | GET | No | API usage stats (used, limit, resets_at, tier) |
| `/history` | GET | Optional | Scoring history with filters |

### Web UI Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/playground` | GET | Interactive API playground |
| `/dashboard` | GET | Web dashboard |
| `/score-form` | GET | Score submission form |
| `/history-page` | GET | History with pagination and filters |
| `/compare` | GET | Side-by-side comparison |
| `/settings` | GET | Settings page |

### Authentication Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register new user |
| `/auth/login` | POST | Login, returns JWT token |
| `/auth/me` | GET | Get current user info |

### Request/Response Schemas

#### POST /score Request

```json
{
  "url": "https://example.com/article",
  "text": "Raw text to score (max 50000 chars)",
  "title": "Optional title"
}
```

Provide either `url` or `text` (not both empty).

#### ScoreResult Response

```json
{
  "overall_score": 35.2,
  "dimensions": {
    "originality": 40.0,
    "info_density": 30.0,
    "reasoning_quality": 25.0,
    "readability": 60.0,
    "timeliness": 50.0,
    "ai_generated_prob": 20.0,
    "emotional_manipulation": 70.0,
    "advertorial_prob": 65.0,
    "scam_prob": 80.0
  },
  "labels": ["scam", "emotional_manipulation"],
  "summary": "内容包含多个诈骗信号",
  "confidence": 0.85,
  "model_used": "deepseek/deepseek-chat",
  "cost": 0.001,
  "scored_at": "2024-01-15T10:30:00Z",
  "scoring_version": "0.3.0"
}
```

#### POST /score/batch Request

```json
{
  "items": [
    {"text": "First article text"},
    {"url": "https://example.com/article2"},
    {"text": "Third text", "title": "Optional title"}
  ]
}
```

#### GET /usage Response

```json
{
  "used": 5,
  "limit": 30,
  "resets_at": "2024-01-16T00:00:00+00:00",
  "tier": "free"
}
```

### Rate Limits

- Free tier: 30 requests/day (resets at midnight UTC)
- Authenticated users: higher limits based on tier

### Error Responses

All errors return JSON with a `detail` field:

```json
{
  "detail": "请提供 'url' 或 'text' 参数"
}
```

Common HTTP status codes:
- `400`: Bad request (invalid input)
- `422`: Validation error (missing required fields)
- `429`: Rate limited
- `500`: Internal server error
- `504`: Upstream timeout (LLM provider)
