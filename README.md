# 鉴真 (Junk Detector)

> 一眼看穿垃圾信息

中文内容质量检测工具 -- 识别诈骗、标题党、软文和垃圾信息。

**零配置即用**：安装后无需任何 API key，规则引擎直接识别明显垃圾内容。

## 安装

```bash
pip install -e .
```

## 使用

### 快速检测（日常推荐）

```bash
# 检测文本
junk-detector quick --text "日入过万 躺赚 财富自由 限时免费 加微信领取"
# 🚨 疑似垃圾内容 (score: 5)

# 管道输入
echo "月入百万 暴利项目 零成本 稳赚不赔" | junk-detector quick
# 🚨 疑似垃圾内容 (score: 5)

# 检测网页
junk-detector quick --url "https://example.com/article"

# 强制仅用规则（永远不调 LLM）
junk-detector quick --rules-only --text "..."
```

### 完整 9 维度评分

需要 LLM API key（DeepSeek/OpenAI/Anthropic/Ollama）：

```bash
export DEEPSEEK_API_KEY=your-key
junk-detector score --text "..." --json
junk-detector score --url "https://..." 
```

### 批量检测

```bash
junk-detector batch --urls-file urls.txt
junk-detector batch --urls-file urls.txt --json
```

### 周期性监控

```bash
junk-detector watch --urls-file urls.txt --interval 3600
```

### 中文信息源监控

主动从中文平台抓取热门内容进行质量检测：

```bash
# 添加微博热搜监控
junk-detector monitor add-source --type weibo

# 添加知乎热榜监控
junk-detector monitor add-source --type zhihu

# 添加微信文章监控（via 搜狗）
junk-detector monitor add-source --type wechat
```

支持的信息源：
| 源 | 类型 | 说明 |
|----|------|------|
| 微博热搜 | JSON API | 实时热搜榜单 |
| 知乎热榜 | JSON API | 热门话题和回答 |
| 微信文章 | HTML 抓取 | 通过搜狗搜索公众号文章 |

### API 服务

```bash
junk-detector serve
# POST /score  GET /health  GET /history
```

### MCP Server (AI 工具集成)

将评分能力暴露为 Agent Skills，支持 Cursor、VSCode Copilot、Claude Code 等 AI 工具直接调用。

```bash
# 启动 MCP 服务
junk-detector mcp-server
```

安装到 AI 工具：将 `mcp-config.json` 添加到你的 AI 工具配置中。

提供 3 个 tools：
- `score_text` — 评分文本内容
- `score_url` — 抓取并评分网页
- `quick_check` — 快速规则检测（无 LLM 调用）

### 实时通知 (WebSocket)

API 服务支持 WebSocket 实时推送评分结果和监控告警：

```bash
# 启动 API 服务（自动包含 WebSocket）
junk-detector serve
```

连接 WebSocket：`ws://localhost:8000/ws`

事件类型：
- `score_completed` — 评分完成时推送结果
- `monitor_alert` — 监控内容低于阈值时告警

邮件通知配置（可选）：

```yaml
# config.yaml
notification:
  websocket: true
  email:
    enabled: true
    smtp_host: smtp.example.com
    smtp_port: 587
    smtp_user: user@example.com
    smtp_pass: password
    to: alert@example.com
```

## 工作原理

```
输入 (text/url/file/stdin)
        │
        ▼
   规则引擎 (201+关键词 + 可信度检测, <1ms, 零成本)
   ├── scam_prob      诈骗概率
   ├── emotional      情绪操纵
   ├── advertorial    软文概率
   ├── ai_generated   AI生成概率
   └── credibility    事实可信度 (伪权威/阴谋论/不可验证声明)
        │
        ├── 高置信度 → 直接返回 (跳过LLM)
        │
        ▼
   LLM Judge (DeepSeek/GPT/Claude, 9维度评分)
   ├── system/user 消息分离 (防prompt注入)
   ├── 输出验证 (检测极端值和注入痕迹)
   └── 低置信度 → 升级到 fallback 模型
        │
        ▼
   加权计算 → 标签生成 → 结果缓存(7天)
```

## 评分维度

**正面维度** (越高越好)：原创性、信息密度、论证质量、可读性、时效性

**风险维度** (越高越危险)：AI生成概率、情绪操纵度、软文概率、骗局概率

## Exit Code (用于脚本)

`quick` 命令的 exit code 有语义：

| Exit Code | 含义 |
|-----------|------|
| 0 | 内容正常 (score >= 60) |
| 1 | 疑似垃圾 (score < 60) |
| 2 | 错误 (参数错误、网络失败等) |

```bash
if junk-detector quick --text "$TEXT"; then
  echo "安全"
else
  echo "垃圾"
fi
```

## Benchmark

Rules engine performance on 500 labeled Chinese content samples:

| Metric | Value |
|--------|-------|
| Precision | 0.99 |
| Recall | 0.80 |
| F1 Score | 0.88 |

Full results: [benchmark/results.md](benchmark/results.md)

Reproduce:
```bash
python benchmark/run_benchmark.py
```

### Real Data Benchmark (100 samples)

Tested against 100 hand-labeled real-world Chinese content samples:

```bash
python benchmark/run_real_benchmark.py
```

**Important caveat**: The rules engine excels at detecting keyword-obvious junk (scam 100%, advertorial 80%) and has zero false positives on quality content. However, **borderline content recall is only 20%** -- the engine essentially cannot distinguish "suspicious but legitimate" from "clean" content without LLM assistance. The 79% overall accuracy reflects perfect performance on clear-cut cases, not general-purpose detection. For borderline/subtle content, the LLM judge fallback is essential.

See [benchmark/real_data/results.md](benchmark/real_data/results.md) for detailed results.

## Custom Rules

Define your own detection rules in `.junk-rules.yaml`:

```bash
# Generate template
junk-detector rules --init

# List all active rules
junk-detector rules --list

# Validate rule file
junk-detector rules --validate my-rules.yaml
```

See [docs/custom-rules.md](docs/custom-rules.md) for full documentation.

## CI/CD Integration

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/kileroppo/junk-detector
    rev: v0.1.0
    hooks:
      - id: junk-detector
```

### GitHub Actions

See [examples/github-action.yml](examples/github-action.yml) for a complete workflow.

```bash
# In your CI script
junk-detector quick --file content.md --threshold 50
```

## PyPI Installation

```bash
pip install junk-detector
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on contributing rules and code.

## 配置

默认使用 DeepSeek（便宜、中文能力强）。支持切换模型：

```bash
junk-detector score --model ollama --text "..."   # 本地 Ollama（免费）
junk-detector score --model openai --text "..."   # GPT-4o-mini
junk-detector score --model anthropic --text "..."  # Claude
```

完整配置见 `config.yaml`。

## 校准反馈

```bash
# 标记某次评分结果为误判
junk-detector feedback --id <content-hash> --verdict junk

# 查看校准统计
junk-detector feedback --stats

# 查看规则改进建议
junk-detector feedback --suggest
```

## 关键词扩展

利用 LLM 对现有规则关键词进行语义扩展，生成同义词、变体写法、混淆形式，提升检测召回率。

```bash
# 预览扩展建议
junk-detector rules --expand

# 指定模型
junk-detector rules --expand --model deepseek/deepseek-chat

# 直接应用到自定义规则文件
junk-detector rules --expand --apply
```

扩展结果缓存在 `~/.cache/junk-detector/expansions.json`，避免重复 LLM 调用。

## 开发

```bash
pip install -e ".[dev]"

# 运行测试 (926+ tests, 90% coverage)
python -m pytest tests/ -q

# 带覆盖率
python -m pytest tests/ --cov=src --cov-fail-under=80

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

## 技术栈

- Python 3.11+
- CLI: Typer + Rich
- LLM: LiteLLM (统一接口)
- API: FastAPI + Uvicorn
- 存储: SQLite
- 测试: pytest + pytest-asyncio

## 设计哲学

> 为道日损，损之又损，以至于无为，无为而无不为。 -- 道德经

- 规则优先，LLM 兜底（成本控制）
- 零配置即用（安装即检测）
- Unix 哲学（管道、exit code、可组合）
- 测试即文档（926+ tests 说明了所有行为）

## Chrome 扩展安装

加载扩展：Chrome → 扩展程序 → 开发者模式 → 加载已解压的扩展程序 → 选择 `extension/` 目录

支持平台：
- 微信公众号 (mp.weixin.qq.com)
- 知乎 (zhihu.com)
- 小红书 (xiaohongshu.com)
- 掘金 (juejin.cn)
- 微博 (weibo.com)

安装后访问支持的平台文章页面，右下角会自动显示内容质量指示器。

## MCP 配置 (Cursor / Claude Code)

将以下配置添加到你的 AI 工具 MCP 设置中：

```json
{
  "mcpServers": {
    "junk-detector": {
      "command": "junk-detector",
      "args": ["mcp-server"]
    }
  }
}
```

提供 3 个 tools：
- `score_text` -- 评分文本内容
- `score_url` -- 抓取并评分网页
- `quick_check` -- 快速规则检测（无 LLM 调用）

## License

MIT
