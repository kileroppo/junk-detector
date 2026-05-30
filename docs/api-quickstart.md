# API 快速上手

## 零配置试用

```bash
# 启动服务
junk-detector serve

# 试用 Demo 端点（无需认证）
curl http://localhost:8000/demo
curl "http://localhost:8000/demo?text=日入过万加微信领取"
```

## 评分文本

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"text": "想要财富自由吗？日入过万不是梦！"}'
```

## 评分 URL

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"url": "https://mp.weixin.qq.com/s/example"}'
```

## 批量评分

```bash
curl -X POST http://localhost:8000/score/batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"text": "这是正常的技术文章内容"},
      {"text": "日入过万 限时免费 加微信领取"},
      {"url": "https://example.com/article"}
    ]
  }'
```

## 查看历史

```bash
# 最近 20 条记录
curl http://localhost:8000/history

# 带过滤条件
curl "http://localhost:8000/history?limit=5&min_score=60"
```

## 健康检查

```bash
# 快速检查
curl http://localhost:8000/health

# 深度检查（验证 LLM 连接）
curl "http://localhost:8000/health?deep=true"
```

## 渐进式使用

1. `/demo` - 零成本体验，规则引擎评分，毫秒级响应
2. `/score` - 单篇深度评分，规则 + LLM 双引擎
3. `/score/batch` - 批量处理，最多 50 篇并发评分

## 返回格式

所有评分接口返回统一的 `ScoreResult` 结构：

```json
{
  "overall_score": 72.5,
  "dimensions": {
    "originality": 75,
    "info_density": 60,
    "reasoning_quality": 70,
    "readability": 80,
    "timeliness": 50,
    "ai_generated_prob": 20,
    "emotional_manipulation": 10,
    "advertorial_prob": 15,
    "scam_prob": 5
  },
  "labels": ["高质量原创"],
  "summary": "内容质量正常",
  "confidence": 0.85,
  "model_used": "deepseek/deepseek-chat"
}
```

## 分数含义

| 分数范围 | 含义 | 建议 |
|---------|------|------|
| 70-100 | 内容质量正常 | 正常阅读 |
| 40-69 | 存在风险信号 | 人工复核 |
| 0-39 | 高风险内容 | 谨慎对待 |
