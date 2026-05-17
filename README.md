# Junk Detector

AI 内容质量评分器 — 基于 LLM-as-Judge + 规则引擎的多维度内容检测工具。

## 功能特点

- **9 维度评分**：原创性、信息密度、论证质量、可读性、时效性、AI生成概率、情绪操纵度、软文概率、骗局概率
- **LLM + 规则混合**：规则层快速识别明显垃圾，LLM 处理复杂判断
- **分级策略**：规则免费 → 便宜模型 → 贵模型复评，优化成本
- **多种输入**：URL 网页抓取（含 SPA 站点）、文本直传、文件读取
- **实时监控**：RSS/Webhook 源自动发现内容并打分（Thunder 模式）
- **任务调度**：优先级队列 + 并发控制 + 指数退避重试（Dispatcher 模式）
- **Web UI**：暗色仪表板，实时查看评分结果和监控状态
- **用户系统**：JWT 认证 + API Key + 用户偏好（自定义权重/阈值/模型）
- **API 限流**：滑动窗口限流，控制 LLM 成本
- **多语言**：中/英双语评分 prompt，按用户偏好切换
- **历史记录**：SQLite 本地存储，支持按分数/标签/日期查询
- **CLI + API + Web**：三种使用方式

## 快速开始

### 安装

```bash
git clone https://github.com/kileroppo/junk-detector.git
cd junk-detector

# 创建虚拟环境（需要 Python 3.11+）
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 基础安装
pip install -e .

# 如需 SPA 网页抓取（掘金、微信公众号等 JS 渲染站点）
pip install -e ".[browser]"
playwright install chromium
```

### 配置

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your-api-key-here

# 可选
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
JWT_SECRET=your-jwt-secret-for-production
```

支持的模型（通过 LiteLLM 统一接口，在 `config.yaml` 中切换）：

| 提供商 | 环境变量 | 特点 |
|--------|---------|------|
| DeepSeek（默认） | `DEEPSEEK_API_KEY` | 便宜，中文好 |
| OpenAI | `OPENAI_API_KEY` | 强大，贵 |
| Anthropic | `ANTHROPIC_API_KEY` | 质量高 |
| Ollama（本地） | 无需 Key | 免费，需本地运行 |

---

## 使用方式

### 1. CLI 命令

#### 评分

```bash
# 评分文本
junk-detector score --text "这篇文章的内容..."

# 评分网页（自动检测 SPA 站点并使用 Playwright）
junk-detector score --url "https://juejin.cn/post/123456"

# 评分文件
junk-detector score --file article.md

# 指定模型
junk-detector score --text "..." --model "openai/gpt-4o-mini"

# JSON 格式输出
junk-detector score --text "..." --json
```

#### 历史记录

```bash
# 查看最近评分
junk-detector history

# 按分数过滤
junk-detector history --min-score 80

# 按标签过滤
junk-detector history --label "疑似骗局"

# 限制条数
junk-detector history --limit 50
```

#### 实时监控

```bash
# 启动实时监控（监听 RSS 源，自动发现并评分新内容）
junk-detector monitor start

# 指定配置文件
junk-detector monitor start --config config.yaml

# 查看监控配置和源列表
junk-detector monitor stats

# 动态添加 RSS 源
junk-detector monitor add-source --name "v2ex" --url "https://www.v2ex.com/feed/tab/tech.xml" --type rss --interval 600
```

#### 启动服务

```bash
# 启动 API + Web UI 服务
junk-detector serve

# 指定端口
junk-detector serve --port 9000
```

---

### 2. Web UI

启动服务后访问 `http://localhost:8000`：

| 页面 | 路径 | 功能 |
|------|------|------|
| 仪表板 | `/dashboard` | 概览统计 + 最近评分（自动刷新） |
| 评分 | `/score-form` | 提交文本/URL 进行评分 |
| 历史 | `/history-page` | 完整历史列表 + 过滤分页 |
| 监控 | `/monitor-status` | Thunder + Dispatcher 实时状态 |

特点：
- 暗色主题（Tailwind CSS）
- HTMX 动态更新（无需刷新页面）
- 移动端适配

---

### 3. API 接口

#### 评分

```bash
# 评分文本
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"text": "文章内容..."}'

# 评分 URL
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'

# 带认证的评分
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"text": "文章内容..."}'
```

#### 历史查询

```bash
curl "http://localhost:8000/history?limit=10&min_score=60&label=疑似软文"
```

#### 健康检查

```bash
curl http://localhost:8000/health
```

#### API 文档

访问 `http://localhost:8000/docs` 查看交互式 OpenAPI 文档。

---

### 4. 用户认证

支持三种认证方式（所有 API 端点向后兼容，无认证也可使用）：

#### 注册 & 登录

```bash
# 注册
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "mypassword"}'

# 登录（获取 JWT Token，24小时有效）
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "mypassword"}'
```

#### 使用认证

```bash
# 方式1: Bearer Token
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" http://localhost:8000/preferences

# 方式2: API Key（注册时返回）
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/score -d '{"text":"..."}'

# 方式3: Query 参数
curl "http://localhost:8000/history?api_key=YOUR_API_KEY"
```

#### 账户管理

```bash
# 查看当前用户信息
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/auth/me

# 重新生成 API Key
curl -X POST -H "Authorization: Bearer TOKEN" http://localhost:8000/auth/regenerate-key
```

---

### 5. 用户偏好

每个用户可自定义评分权重、标签阈值、模型选择和监控源：

```bash
# 查看当前偏好
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/preferences

# 修改评分权重（PATCH — 只更新指定字段）
curl -X PATCH http://localhost:8000/preferences \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scoring_weights": {
      "originality": 1.5,
      "scam_prob": -2.0
    },
    "language": "en"
  }'

# 切换为英文评分
curl -X PATCH http://localhost:8000/preferences \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"language": "en"}'

# 添加个人监控源
curl -X POST http://localhost:8000/preferences/sources \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-blog",
    "type": "rss",
    "url": "https://myblog.com/feed",
    "poll_interval_seconds": 600
  }'

# 查看个人监控源列表
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/preferences/sources

# 删除监控源
curl -X DELETE -H "Authorization: Bearer TOKEN" \
  http://localhost:8000/preferences/sources/my-blog

# 重置偏好为默认
curl -X DELETE -H "Authorization: Bearer TOKEN" http://localhost:8000/preferences
```

---

### 6. 实时监控（Thunder + Dispatcher）

配置文件 `config.yaml` 中的 thunder 段落定义监控源：

```yaml
thunder:
  sources:
    - name: "hacker-news"
      type: rss
      url: "https://hnrss.org/newest"
      poll_interval_seconds: 300
      priority: 5
      enabled: true

    - name: "36kr"
      type: rss
      url: "https://36kr.com/feed"
      poll_interval_seconds: 600
      priority: 5
      enabled: true

  webhook:
    enabled: true
    path: "/webhook/content"

dispatcher:
  max_in_flight: 3
  retry:
    max_attempts: 3
    base_delay_seconds: 2.0
    max_delay_seconds: 60.0
```

通过 Webhook 推送内容：

```bash
# 外部系统推送 URL 到 webhook 进行评分
curl -X POST http://localhost:8000/webhook/content \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/new-article", "title": "New Article"}'
```

---

### 7. API 限流

内置滑动窗口限流，无需额外配置：

| 用户类型 | 限制 | 说明 |
|---------|------|------|
| 认证用户 | 30 rpm | 所有 API 接口 |
| 匿名用户 | 10 rpm | 按 IP 限制 |
| `/score` 接口 | 10 rpm | 控制 LLM 成本 |
| 全局 | 100 rpm | 所有用户合计 |

超限时返回 `429 Too Many Requests`：

```json
{"detail": "Rate limit exceeded", "retry_after_seconds": 60}
```

响应头包含限流信息：
- `X-RateLimit-Limit`: 当前限制
- `X-RateLimit-Remaining`: 剩余请求数
- `X-RateLimit-Reset`: 重置时间戳

---

## 评分维度

| 类型 | 维度 | 说明 |
|------|------|------|
| 正向 | originality | 原创性 vs 洗稿/搬运 |
| 正向 | info_density | 干货比例 |
| 正向 | reasoning_quality | 论证质量（逻辑性/数据支撑） |
| 正向 | readability | 可读性/结构清晰度 |
| 正向 | timeliness | 时效性 |
| 负向 | ai_generated_prob | AI 生成概率 |
| 负向 | emotional_manipulation | 情绪操纵度（标题党/贩卖焦虑） |
| 负向 | advertorial_prob | 商业软文概率 |
| 负向 | scam_prob | 骗子/韭菜收割概率 |

**综合分** = 正向维度加权 - 负向维度加权，归一化到 0-100。

---

## 输出示例

```
📊 Junk Detector 评分结果
━━━━━━━━━━━━━━━━━━━━━━━━━
标题: 无标题
综合评分: 20/100  🚨

📈 正面维度:
  原创性:        10/100
  信息密度:       5/100
  论证质量:       5/100
  可读性:        60/100
  时效性:        20/100

⚠️  风险维度:
  AI生成概率:       20/100
  情绪操纵度:        90/100
  软文概率:         95/100
  骗局概率:         95/100

🏷️  标签: 情绪操纵, 疑似软文, 疑似骗局
💬 总结: 典型的网络诈骗话术，利用暴富幻想和紧迫感诱导加微信，无任何实质信息。
```

---

## 架构

```
junk-detector/
├── src/
│   ├── api/            # FastAPI 主应用 + 限流中间件
│   ├── auth/           # 用户认证 (JWT + API Key + bcrypt)
│   ├── cli/            # Typer CLI (score, history, serve, monitor)
│   ├── core/           # 核心评分逻辑
│   │   ├── scorer.py           # 主编排（分级策略）
│   │   ├── llm_judge.py        # LLM 评分调用
│   │   ├── rules.py            # 规则引擎
│   │   ├── pipeline.py         # 5阶段组合管线
│   │   ├── prompt_loader.py    # 多语言 prompt 加载
│   │   ├── content_filter.py   # 内容违规预过滤
│   │   ├── embeddings.py       # 嵌入 + 相似度检测
│   │   ├── summarizer.py       # 长文摘要
│   │   └── source_reputation.py # 来源信誉系统
│   ├── dispatcher/     # 任务调度 (优先级队列 + 并发 + 重试)
│   ├── extractors/     # 内容提取 (httpx + Playwright SPA)
│   ├── models/         # Pydantic 数据模型
│   ├── monitor/        # Thunder + Dispatcher + Pipeline 集成层
│   ├── preferences/    # 用户偏好 (权重/阈值/源/模型)
│   ├── storage/        # SQLite 持久化
│   ├── thunder/        # 实时流监控 (RSS/Webhook)
│   └── web/            # Web UI (Jinja2 + HTMX + Tailwind)
├── prompts/
│   ├── score_content.txt       # 中文评分 prompt
│   └── score_content_en.txt    # 英文评分 prompt
├── config.yaml         # 全局配置（模型/权重/平台/源/限流）
└── pyproject.toml
```

### 评分流程

```
输入 → 内容提取 → 规则层快判 → LLM评分 → 规则覆盖 → 加权计算 → 生成标签 → 存储 → 输出
         │              │                      │
         ▼              ▼                      ▼
   SPA自动检测     命中明显垃圾            置信度低？
   (Playwright)    直接出分(免费)          → 贵模型复评
```

### 实时监控流程

```
RSS/Webhook → Thunder (发现+去重) → Queue → Dispatcher (并发+重试) → Pipeline → 存储
```

---

## 技术栈

- **Python 3.11+**
- **FastAPI** — API 服务 + 限流中间件
- **Typer + Rich** — CLI 界面
- **Jinja2 + HTMX + Tailwind** — Web UI（无 Node 依赖）
- **LiteLLM** — 统一 LLM 调用（DeepSeek/OpenAI/Claude/Ollama）
- **httpx + BeautifulSoup** — 网页抓取
- **Playwright**（可选）— SPA 站点 JS 渲染
- **SQLite** — 本地历史存储 + 用户数据
- **Pydantic** — 数据模型
- **passlib + python-jose** — 密码哈希 + JWT
- **feedparser** — RSS 解析

---

## 配置参考

完整配置见 `config.yaml`，主要段落：

| 段落 | 功能 |
|------|------|
| `models` | AI 模型配置（4 个提供商） |
| `scoring` | 维度权重 + 标签阈值 |
| `sources` | 来源黑白名单 + 自动拉黑 |
| `platforms` | 平台特定权重（微信/小红书/知乎/博客） |
| `thunder` | 实时监控源配置 |
| `dispatcher` | 任务调度（并发/重试） |
| `rate_limiting` | API 限流参数 |

---

## License

MIT
