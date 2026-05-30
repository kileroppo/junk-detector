# 鉴真 系统状态页规格

## 概述
系统状态页实时展示鉴真各服务的运行状态。

## 状态级别
- 🟢 正常运行 (Operational)
- 🟡 性能下降 (Degraded Performance)
- 🔴 服务中断 (Outage)

## 监控组件
1. API 服务 (/health)
2. 规则引擎 (本地)
3. LLM 评分服务 (DeepSeek/OpenAI)
4. 数据存储 (SQLite/Postgres)

## 展示指标
- 当前状态
- 过去24小时响应时间 (P50, P95, P99)
- 过去30天可用率
- 最近事件记录

## 数据来源
- /health endpoint (每60秒轮询)
- /health?deep=true (每5分钟检查LLM连通性)
- 内部metrics计数器

## 技术实现建议
- 前端: 静态HTML + fetch轮询
- 后端: 新增 /status endpoint 聚合健康数据
- 存储: 时序数据保留30天
