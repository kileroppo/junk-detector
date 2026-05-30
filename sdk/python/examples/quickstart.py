"""鉴真 SDK 快速入门 - 5行代码检测内容质量"""
from sdk.python.jianzhen_client import JianzhenClient

# 创建客户端（默认连接 http://localhost:8000）
client = JianzhenClient()
# 检测一段文本的质量
result = client.score_text("日入过万，加微信免费领取秘籍！限时名额！")
# 查看结果：verdict 可能是 'junk', 'suspicious', 'quality'
print(f"判定: {result['verdict']}, 分数: {result['overall_score']}")
# 查看解释
print(f"解释: {result.get('explanation', '无')}")
