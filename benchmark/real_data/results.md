# Real Data Benchmark Results

> Tested against 100 hand-labeled real-world Chinese content samples.
> This benchmark measures rules-engine-only detection accuracy on
> realistic content without LLM assistance.

## Overall Metrics

- **Total samples**: 100
- **Overall accuracy**: 0.7200

| Metric | Junk | Borderline | Quality |
|--------|------|------------|---------|
| Precision | 0.7500 | 0.5000 | 0.7353 |
| Recall | 0.6000 | 0.2000 | 1.0000 |
| F1 | 0.6667 | 0.2857 | 0.8475 |

## Per-Category Breakdown

| Category | Correct | Total | Accuracy |
|----------|---------|-------|----------|
| advertorial | 7 | 10 | 0.7000 |
| borderline | 4 | 20 | 0.2000 |
| clickbait | 4 | 10 | 0.4000 |
| quality_education | 10 | 10 | 1.0000 |
| quality_news | 10 | 10 | 1.0000 |
| quality_opinion | 5 | 5 | 1.0000 |
| quality_tech | 15 | 15 | 1.0000 |
| quality_zhihu | 10 | 10 | 1.0000 |
| scam | 7 | 10 | 0.7000 |

## False Positives (quality content flagged as junk)

None - no quality content was incorrectly flagged as junk.

## False Negatives (junk content missed)

- **[scam]** 我有个朋友在做资产配置方面的咨询，他们团队做得挺好的，去年帮客户平均实现了比银行理财高不少的回报。如果你对这块感兴趣的话，我可以帮你引荐一下，先聊聊看合不合适，...
- **[scam]** 最近在研究一些新的理财方式，发现有个平台做得挺有意思的，具体我就不多说了，大家可以自己搜一下相关信息。我自己小额试了一下，体验还不错，收益比放银行强。当然投资有...
- **[scam]** 分享一个我最近的经历。去年离职后一直在找新方向，偶然接触到一个社群，里面的人都在做同一个项目。一开始我也半信半疑，但看到群里每天有人晒收入截图，就投了一小笔试试...
- **[clickbait]** 你每天用的那个东西，可能正在慢慢伤害你的身体。很多人完全没有意识到这个问题，包括我之前也是。后来看了一些资料才知道，原来我们习以为常的生活习惯背后有这么大的健康...
- **[clickbait]** 有件事我犹豫了很久要不要发出来。前几天在某个地方看到了一些不太对劲的事情，涉及到一些大家很信任的品牌。我先不说具体是哪家了，但如果你经常买某类产品，建议你关注一...
- **[clickbait]** 说一个我亲眼见到的事情，地点和人物就不透露了。那天我在某个公共场所，无意中听到两个穿西装的人在讨论一件事，内容让我非常吃惊。如果他们说的是真的，那很多人的认知都...
- **[advertorial]** 搬家后一直在寻找一个靠谱的家政阿姨，问了好几个朋友都没有合适推荐。后来邻居介绍了一个平台给我，抱着试试的心态预约了一次深度清洁。阿姨来了之后很专业，三个小时把整...
- **[advertorial]** 最近大家有没有发现某个国产品牌的咖啡味道变好了？我不是什么美食博主，纯粹作为一个每天喝咖啡的普通消费者说说感受。他们好像换了供应商，用了云南的精品豆子。口感比之...

## Weaknesses

Honest assessment of where the rules engine fails:

- **Borderline detection is weak**: The rules engine is binary by nature (matches or not), making it poor at identifying ambiguous content that falls between junk and quality.
- **Misses in scam**: 3 samples from this category were not detected. The rules may need more patterns for this content type.
- **Misses in clickbait**: 3 samples from this category were not detected. The rules may need more patterns for this content type.
- **Misses in advertorial**: 2 samples from this category were not detected. The rules may need more patterns for this content type.
- **Rules cannot assess nuance**: Content quality often depends on context, intent, and factual accuracy that keyword matching cannot capture. The LLM fallback is essential for borderline cases.
- **No semantic understanding**: Rules match surface patterns. A well-written scam that avoids common keywords will evade detection.

## Confusion Details

Examples of misclassified content:

### False Negatives (junk content missed)

- **[scam]** `我有个朋友在做资产配置方面的咨询，他们团队做得挺好的，去年帮客户平均实现了比银行理财高不少的回报。如果你对这块感兴趣的话...`
  - Predicted: quality, Expected: junk
  - Why: Content avoids typical keyword patterns
- **[scam]** `最近在研究一些新的理财方式，发现有个平台做得挺有意思的，具体我就不多说了，大家可以自己搜一下相关信息。我自己小额试了一下...`
  - Predicted: quality, Expected: junk
  - Why: Content avoids typical keyword patterns
- **[scam]** `分享一个我最近的经历。去年离职后一直在找新方向，偶然接触到一个社群，里面的人都在做同一个项目。一开始我也半信半疑，但看到...`
  - Predicted: quality, Expected: junk
  - Why: Content avoids typical keyword patterns
- **[clickbait]** `你每天用的那个东西，可能正在慢慢伤害你的身体。很多人完全没有意识到这个问题，包括我之前也是。后来看了一些资料才知道，原来...`
  - Predicted: quality, Expected: junk
  - Why: Content avoids typical keyword patterns
- **[clickbait]** `有件事我犹豫了很久要不要发出来。前几天在某个地方看到了一些不太对劲的事情，涉及到一些大家很信任的品牌。我先不说具体是哪家...`
  - Predicted: quality, Expected: junk
  - Why: Content avoids typical keyword patterns

## Comparison Notes

### 鉴真 vs 人工审核 vs Perspective API

| 方法 | 优势 | 劣势 |
|------|------|------|
| 鉴真 (规则引擎) | 毫秒级响应, 零成本, 隐私安全 | 无法理解语义, 依赖关键词覆盖 |
| 鉴真 (规则+LLM) | 高准确率, 语义理解 | 有 API 成本, 响应较慢 |
| 人工审核 | 最高准确率, 理解上下文 | 成本高, 不可扩展, 有主观性 |
| Perspective API | 多语言, 成熟稳定 | 针对英文优化, 中文效果有限, 需要网络 |

> **方法论说明**: 本基准仅测试鉴真规则引擎部分。
> 完整的对比测试需要在相同数据集上运行各系统,
> 目前我们没有 Perspective API 的中文测试结果作为对照。
> 上表为定性分析,非定量对比。
