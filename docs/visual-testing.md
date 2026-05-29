# 扩展视觉测试参考

## 状态一: 加载中

**元素状态:**
- verdict-icon: 显示 "⏳"，带 pulse 动画
- explanation: "检测中..." 文字，带 pulse 动画
- score-value: "--"
- 其他元素: 隐藏
- container: 有 .loading class

**视觉要求:**
- 居中对齐
- 动画平滑 (1.5s ease-in-out)
- 无闪烁

## 状态二: 结果显示

**元素状态 (以 "junk" 为例):**
- verdict-icon: "🚨"
- severity-badge: "🚨 危险" (红色)
- explanation: 中文解释文本
- score-value: 数字 (红色, .junk class)
- dismiss-btn: 可见
- menu-btn: 右上角 "☰"

**视觉要求:**
- fadeIn 动画 (0.3s)
- 颜色与严重性匹配
- 文字不超过 3 行

## 状态三: 错误/无内容

**元素状态:**
- verdict-icon: "❓"
- explanation: "请在支持的网站上打开文章后再检测"
- score-value: "--" (灰色)
- dismiss-btn: 隐藏
- daily-stats: 可见 (如果有历史数据)

**视觉要求:**
- 友好的空状态
- 不显示错误堆栈
- 引导用户下一步操作
