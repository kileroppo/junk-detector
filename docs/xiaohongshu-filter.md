# 如何过滤小红书种草软文

本文介绍如何使用 junk-detector 检测小红书平台的种草软文和推广内容。

## 快速开始

```bash
# 安装
pip install junk-detector

# 检测文本内容
junk-detector quick --text "姐妹们！这个真的绝了！用了一周皮肤白了两个度！"
```

## 小红书软文特征

小红书种草软文通常具有以下特征：

| 特征类型 | 典型表现 |
|----------|---------|
| 夸张用词 | 绝了、神仙、yyds、无限回购 |
| 虚假体验 | 用了X天就见效、一周白两个度 |
| 隐性推广 | 链接在评论区、私信问我、@品牌方 |
| 情绪煽动 | 不买后悔、必入、闭眼冲 |
| 刷量话术 | 姐妹们、家人们、集美们 |

## 检测命令

### 基本检测

```bash
# 检测文本
junk-detector quick --text "家人们谁懂啊！这个面膜真的绝了 用了一盒皮肤嫩得跟剥了壳的鸡蛋一样"

# 仅规则引擎
junk-detector quick --rules-only --text "无限回购！好用到哭 链接在评论区"
```

### 设置阈值

小红书内容普遍带有营销属性，可适当调高阈值：

```bash
# 阈值设为 40（更严格）
junk-detector quick --text "..." --threshold 40
```

### 完整评分

```bash
export DEEPSEEK_API_KEY=your-key
junk-detector score --text "姐妹们这个真的必入 品牌方给了独家优惠 拍1发3" --json
```

## 小红书平台检测规则

junk-detector 内置的小红书相关规则涵盖：

- **种草软文** - 检测伪装成真实分享的推广内容
- **虚假测评** - 检测缺乏真实体验的产品推荐
- **引流话术** - 检测引导用户到站外交易的内容
- **数据造假** - 检测含有刷量暗示的内容

## 添加自定义规则

针对特定品类（美妆、母婴、数码等）添加规则：

```bash
junk-detector rules --init
```

编辑 `.junk-rules.yaml`：

```yaml
rules:
  - name: "xiaohongshu-skincare-spam"
    keywords:
      - "白了两个度"
      - "素颜出门"
      - "同事问我用了什么"
    patterns:
      - "用了[一二三四五六七八九十\\d]+[天周月].*(?:效果|变化|改善)"
    target_dimension: "advertorial"
    score_contribution: 30.0
    platform: "xiaohongshu"

  - name: "xiaohongshu-fake-review"
    keywords:
      - "无限回购"
      - "空瓶记"
      - "闭眼入"
      - "不买后悔"
    target_dimension: "advertorial"
    score_contribution: 20.0
    platform: "xiaohongshu"

  - name: "xiaohongshu-traffic-diversion"
    patterns:
      - "(?:链接|方式).*(?:评论|私信|主页)"
      - "(?:私|评论区).*(?:问|找我|dd)"
    target_dimension: "scam_prob"
    score_contribution: 25.0
    platform: "xiaohongshu"
```

验证规则文件：

```bash
junk-detector rules --validate .junk-rules.yaml
junk-detector rules --list
```

## 批量过滤

如果需要批量过滤内容：

```bash
# 将内容逐行放入文件
junk-detector batch --urls-file content-list.txt --json
```

## 在审核流程中使用

```bash
#!/bin/bash
# 自动化审核脚本
CONTENT="$1"

if junk-detector quick --text "$CONTENT" --threshold 40; then
  echo "PASS: 内容通过检测"
  exit 0
else
  echo "REVIEW: 疑似软文，需人工审核"
  exit 1
fi
```

## 注意事项

1. 小红书内容本身带有分享属性，营销倾向检测阈值需适当调整
2. 真实用户分享和软文的边界模糊，建议结合人工审核
3. 使用 `junk-detector feedback` 标记误判可帮助优化规则
