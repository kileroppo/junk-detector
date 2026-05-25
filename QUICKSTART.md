# Quick Start - 5 分钟上手

## 1. 安装

```bash
pip install -e .
```

## 2. 配置 API Key

```bash
export DEEPSEEK_API_KEY=your-key-here
```

## 3. 快速检测 (推荐日常使用)

### 检测文本

```bash
junk-detector quick --text "日入过万！限时免费！加微信领取！"
```

### 检测网页

```bash
junk-detector quick --url "https://example.com/article"
```

### 检测文件

```bash
junk-detector quick --file article.md
```

输出示例:

```
🚨 疑似垃圾内容 (score: 15)
```

## 4. 批量检测

### 从文件读取URL列表

```bash
junk-detector batch --urls-file urls.txt
```

### 从管道输入

```bash
echo "https://example.com/a1\nhttps://example.com/a2" | junk-detector batch --stdin
```

### JSON输出

```bash
junk-detector batch --urls-file urls.txt --json
```

## 5. 完整9维度评分

```bash
junk-detector score --text "..."
junk-detector score --url "https://..." --json
```

## 6. 启动服务

```bash
junk-detector serve
# 访问 http://localhost:8000
```

## 评分阈值说明

| 分数范围 | 含义 |
|---------|------|
| score > 60 | ✅ 正常内容 |
| 40 <= score <= 60 | ⚠️ 需要注意 |
| score < 40 | 🚨 疑似垃圾/诈骗 |

## 更多选项

```
--retry N       设置重试次数 (默认1)
--model xxx     指定模型 (deepseek/openai/anthropic/ollama)
--json          JSON格式输出
```
