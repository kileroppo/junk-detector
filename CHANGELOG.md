# Changelog

所有重要更新记录。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

## [0.3.0] - 2025-01-23

### 新功能
- 直接运行 `junk-detector` 即可看到演示，无需记住子命令
- 评分结果加了边框，截图分享更美观
- 新增 `explain` 命令，交互式了解鉴真如何工作
- 所有评分结果现在包含评分规则版本号 (scoring_version)

### 改进
- 友好的中文错误提示，网络失败、key 缺失等场景都有贴心提示
- 优质内容会收到鼓励和正面评价
- 评分解释根据平台（小红书、公众号）给出针对性说明
- 置信度用自然语言表达，不再是冷冰冰的数字

## [0.2.0] - 2025-01-20

### Added
- API 服务 (FastAPI): /score, /health, /history, /demo 端点
- 用户认证系统 (JWT + API Key)
- WebSocket 实时通知
- 批量评分 (/score/batch) 支持
- SSE 流式响应 (/score/stream)
- 批量文件上传 (/score/batch-upload)
- 真实数据基准测试 (100 样本, 72% 准确率)
- A/B 测试框架 (规则对比)
- 教育性工具提示 ("为什么这是问题?")
- 设计系统文档
- 产品品牌 "鉴真"
- Chrome 扩展: 简化弹窗、严重性分级、键盘快捷键、离线模式
- Chrome 扩展: 历史导出、一键忽略、个人化校准
- Chrome 扩展: 右键菜单检测选中文字
- Python SDK (sdk/python/)
- CLI --profile 选项 (strict/standard/relaxed)
- CLI 非交互模式 (管道输出自动去色)
- 评分来源追踪 (scored_by, duration_ms)
- 友好的 429 限流提示
- 严重性分级系统 (danger/warning/info/safe)
- 操纵技术教育文档 (docs/techniques/)
- 解释质量基准测试

### Changed
- 扩展徽章显示符号 (checkmark/!/X) 代替数字分数
- 限流响应包含用量信息和升级建议
- README 精简为一屏概览

## [0.1.0] - 2025-01-10

### Added
- CLI 工具: score, quick, batch, watch 命令
- 9 维度 LLM 评分 (DeepSeek/OpenAI/Anthropic/Ollama)
- 4 维度快速评分模式
- 本地规则引擎 (诈骗/焦虑/软文关键词)
- 自动跳过 LLM (当规则置信度高时)
- 网页内容提取 (微信/知乎/小红书/掘金/微博)
- Chrome 扩展 (MV3, 本地规则引擎)
- SQLite 存储后端
- 基础基准测试框架
- MCP Server 集成
- 中文信息源监控 (微博/知乎/微信)
