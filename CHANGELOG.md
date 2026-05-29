# Changelog

所有重要更新记录。格式基于 [Keep a Changelog](https://keepachangelog.com/)。

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
