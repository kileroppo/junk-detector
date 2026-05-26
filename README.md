# Junk Detector

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

### API 服务

```bash
junk-detector serve
# POST /score  GET /health  GET /history
```

## 工作原理

```
输入 (text/url/file/stdin)
        │
        ▼
   规则引擎 (201个关键词, <1ms, 零成本)
   ├── scam_prob      诈骗概率
   ├── emotional      情绪操纵
   ├── advertorial    软文概率
   └── ai_generated   AI生成概率
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

## 开发

```bash
pip install -e ".[dev]"

# 运行测试 (602 tests, 90% coverage)
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
- 测试即文档（602 tests 说明了所有行为）

## License

MIT
