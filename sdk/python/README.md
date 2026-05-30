# 鉴真 Python SDK

中文内容质量检测 API 的 Python 客户端。

## 安装

SDK 依赖 httpx:
```bash
pip install httpx
```

## 快速开始

```python
from sdk.python import JianzhenClient

# 初始化客户端
client = JianzhenClient(base_url="http://localhost:8000")

# 检测文本
result = client.score("日入过万 限时免费 加微信领取")
print(f"评分: {result['overall_score']}")
print(f"标签: {result['labels']}")

# 检测网页
result = client.score_url("https://mp.weixin.qq.com/s/example")

# 试用 demo 端点 (无需 API key)
demo = client.demo("想要财富自由吗？")
print(f"判定: {demo['verdict']}")

# 健康检查
health = client.health()
print(f"状态: {health['status']}")
```

## API Key

免费版不需要 API key。专业版需要在初始化时提供:

```python
client = JianzhenClient(api_key="your-api-key")
```
