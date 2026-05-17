# Junk Detector

AI 内容质量评分器 — 基于 LLM-as-Judge + 规则引擎的多维度内容检测工具。

## 功能特点

- **9 维度评分**：原创性、信息密度、论证质量、可读性、时效性、AI生成概率、情绪操纵度、软文概率、骗局概率
- **LLM + 规则混合**：规则层快速识别明显垃圾，LLM 处理复杂判断
- **分级策略**：规则免费 → 便宜模型 → 贵模型复评，优化成本
- **多种输入**：URL 网页抓取、文本直传、文件读取
- **历史记录**：SQLite 本地存储，支持按分数/标签/日期查询
- **CLI + API**：命令行即时评分 + FastAPI 后端服务

## 快速开始

### 安装

```bash
git clone https://github.com/kileroppo/junk-detector.git
cd junk-detector

# 创建虚拟环境（需要 Python 3.11+）
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装
pip install -e .
```

### 配置

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your-api-key-here
```

支持的模型配置（通过 LiteLLM 统一接口）：
- DeepSeek（默认）：`DEEPSEEK_API_KEY`
- OpenAI：`OPENAI_API_KEY`
- Claude：`ANTHROPIC_API_KEY`

### 使用

#### CLI 命令

```bash
# 评分文本
junk-detector score --text "文章内容..."

# 评分网页
junk-detector score --url "https://example.com/article"

# 评分文件
junk-detector score --file article.md

# JSON 格式输出
junk-detector score --text "..." --json

# 查看历史
junk-detector history
junk-detector history --min-score 80
junk-detector history --label "疑似骗局"

# 启动 API 服务
junk-detector serve
junk-detector serve --port 9000
```

#### API 接口

```bash
# 启动服务后

# 评分文本
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"text": "文章内容..."}'

# 评分 URL
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'

# 查看历史
curl "http://localhost:8000/history?limit=10&min_score=60"

# 健康检查
curl http://localhost:8000/health

# API 文档
open http://localhost:8000/docs
```

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

## 架构

```
junk-detector/
├── src/
│   ├── api/            # FastAPI 路由
│   ├── cli/            # Typer CLI 入口
│   ├── core/           # 核心评分逻辑
│   │   ├── scorer.py       # 主编排（分级策略）
│   │   ├── llm_judge.py    # LLM 评分调用
│   │   └── rules.py        # 规则引擎
│   ├── extractors/     # 内容提取
│   │   ├── web.py          # 网页抓取
│   │   └── text.py         # 文本/文件
│   ├── models/         # Pydantic 数据模型
│   └── storage/        # SQLite 存储层
├── prompts/            # LLM prompt 模板
└── tests/
```

### 评分流程

```
输入 → 内容提取 → 规则层快判 → LLM评分 → 规则覆盖 → 加权计算 → 生成标签 → 存储 → 输出
                        │                      │
                        ▼                      ▼
                  命中明显垃圾            置信度低？
                  直接出分(免费)          → 贵模型复评
```

## 技术栈

- **Python 3.11+**
- **FastAPI** — API 服务
- **Typer + Rich** — CLI 界面
- **LiteLLM** — 统一 LLM 调用（支持 DeepSeek/OpenAI/Claude 等）
- **httpx + BeautifulSoup** — 网页抓取
- **SQLite** — 本地历史存储
- **Pydantic** — 数据模型

## License

MIT
