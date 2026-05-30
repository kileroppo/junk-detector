# 鉴真 完整使用指南

## 快速检测（日常推荐）

```bash
# 检测文本
junk-detector quick --text "日入过万 躺赚 财富自由 限时免费 加微信领取"

# 检测网页
junk-detector quick --url "https://example.com/article"

# 强制仅用规则（永远不调 LLM）
junk-detector quick --rules-only --text "..."

# 配置 profile (严格/标准/宽松)
junk-detector quick --profile strict --text "..."
```

## 完整 9 维度评分

需要 LLM API key（DeepSeek/OpenAI/Anthropic/Ollama）：

```bash
export DEEPSEEK_API_KEY=your-key
junk-detector score --text "..." --json
junk-detector score --url "https://..."
```

### 评分维度

**正面维度** (越高越好)：原创性、信息密度、论证质量、可读性、时效性

**风险维度** (越高越危险)：AI生成概率、情绪操纵度、软文概率、骗局概率

## 批量检测

```bash
junk-detector batch --urls-file urls.txt
junk-detector batch --urls-file urls.txt --json
```

## 周期性监控

```bash
junk-detector watch --urls-file urls.txt --interval 3600
```

## 中文信息源监控

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

## 平台登录认证

部分平台（知乎、微博、小红书等）需要登录才能正常抓取内容。鉴真提供了通用的 Cookie 认证模块。

### 登录平台

```bash
# 登录知乎（会打开浏览器，扫码或手动登录）
junk-detector auth login --platform zhihu

# 登录其他平台
junk-detector auth login --platform weibo
junk-detector auth login --platform xiaohongshu
junk-detector auth login --platform bilibili
junk-detector auth login --platform wechat
```

登录完成后，Cookie 自动保存（默认有效期 7 天），后续检测该平台内容无需重复登录。

### 查看登录状态

```bash
junk-detector auth status
```

### 登出

```bash
# 登出单个平台
junk-detector auth logout --platform zhihu

# 登出所有平台
junk-detector auth logout --all
```

### 工作原理

检测 URL 时，系统自动识别平台并按以下顺序尝试：

1. 直接请求（浏览器 UA + headers）
2. 使用已保存的 Cookie 认证请求
3. Playwright 无头浏览器渲染（需安装 `[browser]` 依赖）
4. 若全部失败，提示用户登录

### 安装要求

```bash
# 基础安装（httpx 即可，支持 cookie 认证）
pip install -e .

# 完整安装（支持浏览器登录 + Playwright 渲染）
pip install -e ".[browser]"
playwright install chromium
```

### 作为独立模块使用

`crawler_auth` 模块零依赖于鉴真其它模块，可直接在其他项目中复用：

```python
from src.crawler_auth import AuthenticatedClient, CookieStore

client = AuthenticatedClient()

# 自动识别平台 + 带 cookie 请求
response = await client.fetch("https://www.zhihu.com/question/123/answer/456")

# 检测平台
platform = client.detect_platform("https://weibo.com/...")  # -> "weibo"
```

支持的平台：

| 平台 | 域名 | 登录方式 |
|------|------|----------|
| 知乎 | zhihu.com | 扫码/密码 |
| 微博 | weibo.com | 扫码/密码 |
| 小红书 | xiaohongshu.com | 扫码 |
| B站 | bilibili.com | 扫码/密码 |
| 微信/搜狗 | weixin.sogou.com | 减少验证码频率 |

## API 服务

```bash
junk-detector serve
# POST /score  GET /health  GET /history  GET /demo
```

详见 [API 快速开始](api-quickstart.md)。

## MCP Server (AI 工具集成)

将评分能力暴露为 Agent Skills，支持 Cursor、VSCode Copilot、Claude Code 等 AI 工具直接调用。

```bash
# 启动 MCP 服务
junk-detector mcp-server
```

提供 3 个 tools：
- `score_text` -- 评分文本内容
- `score_url` -- 抓取并评分网页
- `quick_check` -- 快速规则检测（无 LLM 调用）

MCP 配置：
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

## 实时通知 (WebSocket)

```bash
junk-detector serve
```

连接 WebSocket：`ws://localhost:8000/ws`

事件类型：
- `score_completed` -- 评分完成时推送结果
- `monitor_alert` -- 监控内容低于阈值时告警

## Exit Code (用于脚本)

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

## 自定义规则

```bash
# 生成模板
junk-detector rules --init

# 列出所有规则
junk-detector rules --list

# 验证规则文件
junk-detector rules --validate my-rules.yaml
```

详见 [自定义规则文档](custom-rules.md)。

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

```bash
# 预览扩展建议
junk-detector rules --expand

# 直接应用到自定义规则文件
junk-detector rules --expand --apply
```

## 配置

默认使用 DeepSeek（便宜、中文能力强）。支持切换模型：

```bash
junk-detector score --model ollama --text "..."   # 本地 Ollama（免费）
junk-detector score --model openai --text "..."   # GPT-4o-mini
junk-detector score --model anthropic --text "..."  # Claude
```

完整配置见 `config.yaml`。
