# 如何审核微信公众号文章

本文介绍如何使用 junk-detector 审核微信公众号文章的内容质量。

## 快速开始

```bash
# 安装
pip install junk-detector

# 检测单篇文章
junk-detector quick --url "https://mp.weixin.qq.com/s/xxxxx"
```

## 常见检测场景

### 检测软文

微信公众号是软文高发平台。junk-detector 内置了针对微信平台的检测规则：

```bash
# 检测单篇
junk-detector quick --url "https://mp.weixin.qq.com/s/example"

# 仅用规则引擎（不调用 LLM，速度更快）
junk-detector quick --rules-only --url "https://mp.weixin.qq.com/s/example"
```

### 批量检测

将多个文章链接放入文件，逐行一个 URL：

```bash
# urls.txt 内容示例：
# https://mp.weixin.qq.com/s/article1
# https://mp.weixin.qq.com/s/article2

junk-detector batch --urls-file wechat-urls.txt
```

### 完整评分

需要 LLM API key 才能获得 9 维度评分：

```bash
export DEEPSEEK_API_KEY=your-key
junk-detector score --url "https://mp.weixin.qq.com/s/example" --json
```

## 微信平台特有检测模式

junk-detector 对微信公众号内容有专门的检测规则，包括：

| 模式类型 | 示例关键词 |
|----------|-----------|
| 课程营销 | 训练营、知识付费、私域、社群 |
| 引流话术 | 加微信、扫码领取、关注回复 |
| 虚假背书 | 央视推荐、专家认证、百万粉丝 |
| 情绪操纵 | 震惊、不转不是中国人、看完哭了 |
| 诈骗话术 | 日入过万、稳赚不赔、限时免费 |

## 添加自定义微信规则

如果内置规则不够，可以添加自定义规则：

```bash
# 生成规则模板
junk-detector rules --init
```

编辑 `.junk-rules.yaml`：

```yaml
rules:
  - name: "wechat-health-scam"
    keywords:
      - "偏方治大病"
      - "医院不告诉你"
      - "一招根治"
    target_dimension: "scam_prob"
    score_contribution: 45.0
    platform: "wechat"

  - name: "wechat-fake-giveaway"
    patterns:
      - "转发.*(?:领|得|送)"
      - "点赞.*(?:抽奖|送)"
    target_dimension: "scam_prob"
    score_contribution: 30.0
    platform: "wechat"
```

验证规则：

```bash
junk-detector rules --validate .junk-rules.yaml
```

## 在脚本中使用

利用 exit code 进行自动化判断：

```bash
#!/bin/bash
URL="https://mp.weixin.qq.com/s/example"

if junk-detector quick --url "$URL" --threshold 50; then
  echo "文章质量合格"
else
  echo "文章质量不达标，需要人工审核"
fi
```

## 常见问题

### 微信文章无法抓取？

某些微信文章有反爬保护。如果遇到抓取失败，可以：

1. 手动复制文章文本，使用 `--text` 参数检测
2. 安装 playwright 扩展：`pip install junk-detector[browser]`

### 如何降低误判率？

- 使用 `--threshold` 调整阈值（默认 60）
- 对特定公众号的风格使用自定义规则微调
- 使用 `junk-detector feedback` 标记误判，帮助规则优化
