# CI/CD 集成指南

本文介绍如何将 junk-detector 集成到持续集成/持续部署流程中。

## Pre-commit Hook

使用 [pre-commit](https://pre-commit.com/) 在提交前自动检测内容质量。

### 安装 pre-commit

```bash
pip install pre-commit
```

### 配置

在项目根目录创建 `.pre-commit-config.yaml`：

```yaml
repos:
  - repo: https://github.com/kileroppo/junk-detector
    rev: v0.1.0
    hooks:
      - id: junk-detector
        name: Content Quality Check
        types: [markdown, text]
        args: ['--threshold', '50']
```

### 安装 hook

```bash
pre-commit install
```

之后每次 `git commit` 时会自动检测修改的 markdown 和文本文件。

## GitHub Actions

### 基本配置

```yaml
# .github/workflows/content-check.yml
name: Content Quality Check
on:
  pull_request:
    paths:
      - 'content/**'
      - 'posts/**'

jobs:
  check-content:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install junk-detector
      - name: Check content quality
        run: |
          FAILED=0
          for file in $(git diff --name-only HEAD~1 -- 'content/**' 'posts/**'); do
            if [ -f "$file" ]; then
              echo "Checking: $file"
              if ! junk-detector quick --file "$file" --threshold 50; then
                FAILED=1
                echo "::warning file=$file::Content quality below threshold"
              fi
            fi
          done
          exit $FAILED
```

完整示例见 [examples/github-action.yml](../examples/github-action.yml)。

## GitLab CI

```yaml
# .gitlab-ci.yml
content-quality:
  stage: test
  image: python:3.11-slim
  script:
    - pip install junk-detector
    - |
      FAILED=0
      for file in $(git diff --name-only HEAD~1 -- 'content/**'); do
        if [ -f "$file" ]; then
          echo "Checking: $file"
          if ! junk-detector quick --file "$file" --threshold 50; then
            FAILED=1
          fi
        fi
      done
      exit $FAILED
  only:
    changes:
      - content/**
```

## Exit Codes

junk-detector 的 `quick` 命令使用语义化 exit code，方便脚本集成：

| Exit Code | 含义 | CI 行为 |
|-----------|------|---------|
| 0 | 内容质量合格 (score >= threshold) | 通过 |
| 1 | 疑似垃圾内容 (score < threshold) | 失败 |
| 2 | 运行错误（参数错误、网络失败等） | 错误 |

### 在 Shell 脚本中使用

```bash
#!/bin/bash
set -e

junk-detector quick --file "$FILE" --threshold 50
status=$?

case $status in
  0) echo "Content OK" ;;
  1) echo "Content flagged as low quality" ; exit 1 ;;
  2) echo "Error running detector" ; exit 2 ;;
esac
```

## 阈值配置

`--threshold` 参数控制通过/失败的分界线：

| 阈值 | 严格程度 | 适用场景 |
|------|---------|---------|
| 70 | 宽松 | 个人博客、内部文档 |
| 60 | 默认 | 通用内容审核 |
| 50 | 较严 | 公开发布内容 |
| 40 | 严格 | 品牌官方内容 |

```bash
# 宽松模式
junk-detector quick --file content.md --threshold 70

# 严格模式
junk-detector quick --file content.md --threshold 40
```

## 仅规则引擎模式

在 CI 中推荐使用 `--rules-only` 模式，无需 API key，速度快：

```bash
junk-detector quick --rules-only --file content.md --threshold 50
```

优势：
- 无需配置 LLM API key
- 执行速度 <1ms
- 零成本
- 确定性结果（同输入同输出）
