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

Cookie 保存在本地：`~/.crawler_auth/cookies/<platform>.json`，默认有效期 7 天。

### 导入 Cookie（日常推荐）

**最省事的更新方式**：在浏览器复制 Cookie，终端一条命令写入，无需手动改文件。

#### 知乎（需搜索页 Cookie）

知乎搜索接口需要搜索页产生的 Cookie（如 `z_c0`、`__zse_ck`），仅登录页 Cookie 可能不够用。

**推荐流程：**

1. 浏览器登录 [知乎](https://www.zhihu.com)，打开任意搜索页，例如：  
   `https://www.zhihu.com/search?type=content&q=test`
2. 打开 DevTools → **Network**，刷新页面，点任意请求 → **Headers** → 复制 `Cookie` 整行  
   （或 Application → Cookies → `zhihu.com` 下全部项）
3. 复制到剪贴板后执行：

```bash
junk-detector auth import --platform zhihu
```

不传 `--cookie` / `--file` 时，**默认从系统剪贴板读取**。

#### 微博（需 H5 版 Cookie）

微博抓取默认使用 **H5 移动版**（`m.weibo.cn`）Cookie，桌面版 `weibo.com` 的 Cookie 通常无效。

**推荐流程：**

1. 手机浏览器或 Chrome 设备模拟登录 [m.weibo.cn](https://m.weibo.cn/)  
   （Chrome DevTools → Toggle device toolbar，选 iPhone，再访问 `https://m.weibo.cn/`）
2. 登录后打开 H5 搜索页，例如：  
   `https://m.weibo.cn/search?containerid=100103type%3D1%26q%3Dtest`
3. DevTools → **Network** → 刷新 → 复制任意请求的 `Cookie`  
   （或 Application → Cookies → `m.weibo.cn` / `weibo.cn` 下全部项）
4. 复制到剪贴板后执行：

```bash
junk-detector auth import --platform weibo
```

常见 H5 Cookie 字段：`SUB`、`SUBP`、`_T_WM`、`XSRF-TOKEN`（域名 `weibo.cn`）。

#### 命令参考

```bash
# 从剪贴板导入（默认，推荐）
junk-detector auth import --platform zhihu

# 显式指定剪贴板
junk-detector auth import --platform zhihu --clipboard

# 直接粘贴 Cookie 字符串
junk-detector auth import --platform zhihu --cookie "z_c0=...; __zse_ck=..."
junk-detector auth import --platform weibo --cookie "SUB=...; SUBP=...; _T_WM=..."

# 从文件读取（整行 Cookie 或 JSON 均可）
junk-detector auth import --platform zhihu --file ~/cookies.txt
junk-detector auth import --platform weibo --file ~/weibo-cookies.txt
```

#### 合并与替换

| 行为 | 命令 | 说明 |
|------|------|------|
| 合并（默认） | `auth import -p zhihu` | 新 Cookie 覆盖同名项，保留未提供的旧项 |
| 完全替换 | `auth import -p zhihu --replace` | 丢弃旧 Cookie，只保留本次导入的 |

知乎、微博示例：

```bash
junk-detector auth import -p zhihu          # 合并知乎搜索页 Cookie
junk-detector auth import -p weibo          # 合并微博 H5 Cookie
junk-detector auth import -p weibo --replace # 完全替换微博 Cookie
```

支持的输入格式：

- 分号分隔：`z_c0=abc; __zse_ck=def`
- 带前缀的 Request Header：`Cookie: z_c0=abc; __zse_ck=def`
- JSON 对象：`{"z_c0": "abc", "__zse_ck": "def"}`

导入后验证：

```bash
junk-detector auth status
```

### Web UI 管理（推荐）

启动服务后，在 **设置页** 管理 Cookie 与模型 API：

```bash
junk-detector serve
# 设置 → http://localhost:8000/settings
# Cookie 区块 → http://localhost:8000/settings#cookies
# 模型配置   → http://localhost:8000/settings#model
```

**Cookie 管理：**

- 查看所有已注册平台的 Cookie 状态（已配置 / 已过期 / 未配置）
- 粘贴 Cookie 一键导入（默认合并）
- 按平台清除 Cookie

**模型配置：**

- 选择提供商：DeepSeek、OpenAI、Anthropic、智谱、Moonshot、Ollama、自定义/中转
- 配置 **API Base URL**、**API Key**、**模型**
- 自定义/中转：填 OpenAI 兼容 Base URL + 模型 ID + Key
- 配置保存在 `~/.junk_detector/settings.json`（本地，权限 600）

**评分权重：**

- 设置 → **评分权重**（`/settings#weights`）
- 拖动滑块调整 9 个维度权重，点击「保存权重」
- 「恢复默认」会读回 `config.yaml` 中的系统默认值
- 保存后对 Web 端评分立即生效（CLI `score` 仍读 `config.yaml`，除非通过 `/preferences` API 配置）

新增平台时，在 `src/crawler_auth/platform_meta.py` 添加条目即可自动出现在 Cookie 区块。

**扩展新平台（两步）：**

1. 在 `src/crawler_auth/platforms/` 实现认证类，并注册到 `PLATFORMS`
2. 在 `src/crawler_auth/platform_meta.py` 的 `PLATFORM_META` 添加展示信息：

```python
"newplatform": {
    "label": "新平台",
    "domain": "example.com",
    "hint": "Cookie 获取说明",
    "guide_url": "https://example.com/login",
    "key_cookies": ["session_id"],
},
```

保存后刷新 **设置 → 平台 Cookie** 即可看到新平台卡片。

### 浏览器登录

若已安装 Playwright，也可用浏览器自动登录并保存 Cookie：

```bash
# 登录知乎（打开浏览器，扫码或手动登录；登录后会自动访问搜索页再保存）
junk-detector auth login --platform zhihu

# 登录微博（H5 移动版；登录后会自动访问 m.weibo.cn 搜索页再保存）
junk-detector auth login --platform weibo

# 登录其他平台
junk-detector auth login --platform xiaohongshu
junk-detector auth login --platform bilibili
junk-detector auth login --platform wechat
```

登录完成后 Cookie 自动保存，后续检测该平台内容无需重复登录。

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

| 平台 | 域名 | 推荐方式 | 说明 |
|------|------|----------|------|
| 知乎 | zhihu.com | `auth import` | 需搜索页 Cookie；`auth login` 登录后会自动访问搜索页 |
| 微博 | m.weibo.cn | `auth import` | 需 H5 移动版 Cookie（`weibo.cn` 域）；桌面版无效 |
| 小红书 | xiaohongshu.com | 扫码 | |
| B站 | bilibili.com | 扫码/密码 | |
| 微信/搜狗 | weixin.sogou.com | 减少验证码频率 | |

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
