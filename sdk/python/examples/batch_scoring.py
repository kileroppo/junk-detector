"""鉴真 SDK 批量评分示例 - 一次请求评多篇内容"""
from sdk.python.jianzhen_client import JianzhenClient

# 创建客户端
client = JianzhenClient(base_url="http://localhost:8000")

# 准备多条待检测内容
texts = [
    "深度学习在自然语言处理中的最新进展综述",
    "震惊！99%的人不知道的赚钱秘密，限时免费！",
    "如何科学地进行时间管理：番茄工作法实践指南",
]

# 批量评分（单次API调用，高效）
results = client.score_batch([{"text": t} for t in texts])

# 遍历结果
for i, result in enumerate(results):
    print(f"[{i+1}] {texts[i][:20]}...")
    print(f"    判定: {result['verdict']} | 分数: {result['overall_score']}")
    print()
