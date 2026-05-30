# 鉴真 (Jianzhen)

> **鉴真 — 一眼看穿**

一眼看穿垃圾信息。

中文内容质量检测工具 -- 识别诈骗、标题党、软文和垃圾信息。

## 快速开始

```bash
pip install -e .
junk-detector demo
```

## 检测内容

```bash
# 规则引擎 (零配置, 毫秒级)
junk-detector quick --text "日入过万 限时免费 加微信领取" --rules-only
# 🚨 疑似垃圾内容 (score: 5)

# 管道输入
echo "月入百万 暴利项目" | junk-detector quick --rules-only
```

## 浏览器扩展

支持微信公众号、知乎、小红书、掘金、微博。安装后自动检测。

## 文档

- [完整使用指南](docs/usage.md)
- [API 快速开始](docs/api-quickstart.md)
- [Python SDK](sdk/python/README.md)
- [平台登录认证](docs/usage.md#平台登录认证)
- [定价方案](docs/pricing.md)
- [品牌标识](docs/brand.md)
- [更新日志](CHANGELOG.md)

## License

MIT
