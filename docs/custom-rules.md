# 自定义规则指南

本文介绍如何创建和管理自定义检测规则。

## 规则文件位置

junk-detector 按以下顺序查找自定义规则：

1. 当前目录下的 `.junk-rules.yaml`
2. 用户主目录下的 `~/.junk-detector/rules.yaml`

两个文件都存在时，规则会合并（当前目录优先）。

## 快速开始

```bash
# 生成规则模板文件
junk-detector rules --init

# 查看所有活跃规则
junk-detector rules --list

# 验证规则文件
junk-detector rules --validate .junk-rules.yaml
```

## YAML Schema

```yaml
rules:
  - name: "rule-name"              # 必填，规则名称
    keywords: ["keyword1"]         # 可选，关键词列表
    patterns: ["regex\\d+"]        # 可选，正则表达式列表
    target_dimension: "scam_prob"  # 必填，目标维度
    score_contribution: 25.0       # 必填，分数贡献 (0-100)
    platform: null                 # 可选，限定平台
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 规则唯一名称 |
| keywords | list[string] | 否* | 匹配的关键词 |
| patterns | list[string] | 否* | 匹配的正则表达式 |
| target_dimension | string | 是 | 目标评分维度 |
| score_contribution | float | 是 | 匹配时贡献的分数 |
| platform | string/null | 否 | 限定生效平台 |

*`keywords` 和 `patterns` 至少需要一个。

### target_dimension 可选值

- `scam_prob` - 诈骗概率
- `emotional` - 情绪操纵度
- `advertorial` - 软文概率
- `ai_generated` - AI 生成概率

### platform 可选值

- `"wechat"` - 微信公众号
- `"xiaohongshu"` - 小红书
- `"douyin"` - 抖音
- `"weibo"` - 微博
- `null` - 所有平台（默认）

## 示例

### 检测加密货币诈骗

```yaml
rules:
  - name: "crypto-scam"
    keywords:
      - "稳赚不赔"
      - "保本保息"
      - "日化收益"
      - "躺赚"
    patterns:
      - "(?:日|月)(?:入|赚)[\\d万]+"
    target_dimension: "scam_prob"
    score_contribution: 45.0
```

### 检测情绪操纵标题

```yaml
rules:
  - name: "clickbait-titles"
    keywords:
      - "震惊"
      - "万万没想到"
      - "看完哭了"
      - "不转不是中国人"
    target_dimension: "emotional"
    score_contribution: 30.0
```

### 微信平台专用规则

```yaml
rules:
  - name: "wechat-course-selling"
    keywords:
      - "训练营"
      - "私域变现"
      - "社群运营"
    patterns:
      - "原价\\d+.*现价\\d+"
      - "(?:前|限)\\d+名.*(?:免费|优惠)"
    target_dimension: "advertorial"
    score_contribution: 25.0
    platform: "wechat"
```

## CLI 命令

### 初始化规则文件

```bash
junk-detector rules --init
```

在当前目录生成 `.junk-rules.yaml` 模板文件。

### 查看活跃规则

```bash
junk-detector rules --list
```

显示内置规则数量和所有自定义规则名称。

### 验证规则文件

```bash
junk-detector rules --validate my-rules.yaml
```

检查规则文件的格式和内容是否正确，报告所有错误。

## 规则合并逻辑

自定义规则与内置规则的合并方式：

1. 内置规则始终生效
2. 自定义规则在内置规则之后执行
3. 所有匹配规则的 `score_contribution` 累加
4. 每个维度的最终分数不超过 100

## 编写有效规则的建议

1. **关键词要精准** - 避免太宽泛的词（如"免费"），选择组合出现才有意义的词
2. **正则要节制** - 复杂正则影响性能，优先用关键词
3. **分数要合理** - 单个规则贡献 10-40 分为宜，避免单规则直接触顶
4. **测试要充分** - 用真实内容测试，确保不会误伤正常内容
5. **平台要限定** - 如果规则只在某平台有意义，务必指定 `platform`

## 调试

如果规则不生效，检查：

```bash
# 确认规则文件被加载
junk-detector rules --list

# 验证规则格式
junk-detector rules --validate .junk-rules.yaml

# 测试规则匹配
junk-detector quick --rules-only --text "测试内容包含关键词"
```
