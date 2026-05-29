# Rule Format Specification

This document describes the YAML schema for custom detection rules.

## Schema

```yaml
rules:
  - name: string          # Required. Descriptive rule name (unique identifier)
    keywords: [string]    # Optional. List of keywords to match
    patterns: [string]    # Optional. List of regex patterns to match
    target_dimension: string  # Required. Which scoring dimension this rule affects
    score_contribution: float # Required. Points added when rule matches (0-100)
    platform: string | null   # Optional. Limit rule to specific platform
```

## Fields

### name (required)

A unique, descriptive name for the rule. Used in reporting and CLI output.

- Must be a non-empty string
- Should describe what the rule detects
- Examples: `"crypto-scam-keywords"`, `"wechat-course-selling"`, `"emotional-clickbait"`

### keywords (optional)

List of keywords to match against content. Matching is case-insensitive and checks for substring presence.

```yaml
keywords:
  - "日入过万"
  - "财富自由"
  - "限时免费"
```

At least one of `keywords` or `patterns` must be provided.

### patterns (optional)

List of regex patterns to match against content. Uses Python `re` module syntax.

```yaml
patterns:
  - "加[微vV]信[\\w]{5,}"
  - "\\d{5,}元"
  - "(扫码|点击).{0,10}(领取|获取)"
```

At least one of `keywords` or `patterns` must be provided.

### target_dimension (required)

Which scoring dimension this rule contributes to. Allowed values:

| Value | Description |
|-------|-------------|
| `scam_prob` | Scam/fraud probability |
| `emotional` | Emotional manipulation score |
| `advertorial` | Advertorial/sponsored content probability |
| `ai_generated` | AI-generated content probability |

### score_contribution (required)

How many points this rule adds to the target dimension when matched. Value between 0 and 100.

- Contributions are additive across all matching rules
- Final dimension score is capped at 100
- Typical values: 10-30 for weak signals, 40-60 for strong signals

### platform (optional)

Restrict this rule to content from a specific platform. When null or omitted, the rule applies to all content.

Supported platform values:
- `"wechat"` - WeChat / mp.weixin.qq.com
- `"xiaohongshu"` - Xiaohongshu / RED
- `"douyin"` - Douyin / TikTok China
- `"weibo"` - Sina Weibo
- `null` - All platforms (default)

## Scoring Logic

1. Each rule is evaluated independently against the content
2. If any keyword or pattern matches, the rule fires
3. The `score_contribution` is added to the `target_dimension`
4. Multiple rules can fire and their contributions stack
5. Each dimension is capped at 100

## Examples

### Basic Scam Detection

```yaml
rules:
  - name: "crypto-scam"
    keywords:
      - "稳赚不赔"
      - "保本保息"
      - "日化收益"
    target_dimension: "scam_prob"
    score_contribution: 40.0
```

### Platform-Specific Rule

```yaml
rules:
  - name: "wechat-course-selling"
    keywords:
      - "训练营"
      - "私域"
      - "知识付费"
    patterns:
      - "原价\\d+.{0,5}现价\\d+"
    target_dimension: "advertorial"
    score_contribution: 25.0
    platform: "wechat"
```

### Regex Pattern Rule

```yaml
rules:
  - name: "contact-info-spam"
    patterns:
      - "加[微vV]信[：:]?\\s*[a-zA-Z0-9_]{5,}"
      - "(?:QQ|qq)[：:]?\\s*\\d{6,}"
      - "\\d{11}"  # Phone numbers
    target_dimension: "scam_prob"
    score_contribution: 30.0
```

### Multiple Rules File

```yaml
rules:
  - name: "urgency-manipulation"
    keywords:
      - "仅剩最后"
      - "即将涨价"
      - "错过再等一年"
    target_dimension: "emotional"
    score_contribution: 20.0

  - name: "fake-authority"
    keywords:
      - "央视推荐"
      - "专家认证"
      - "国家认可"
    patterns:
      - "(?:已有|超过)\\d+万人"
    target_dimension: "scam_prob"
    score_contribution: 35.0
```
