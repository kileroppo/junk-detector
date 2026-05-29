/**
 * rules.js - Local keyword-based scoring engine for Chinese content quality detection.
 *
 * Ported from src/core/rules.py - top 50 most impactful keywords across 3 categories.
 * Runs entirely in the browser with no external API calls.
 */

// Top 20 scam keywords (from _SCAM_KEYWORDS in rules.py)
const SCAM_KEYWORDS = [
  "日入过万",
  "躺赚",
  "财富自由",
  "限时免费",
  "私聊领取",
  "月入百万",
  "被动收入",
  "零成本",
  "稳赚不赔",
  "加微信",
  "免费领取",
  "名额有限",
  "最后一天",
  "一夜暴富",
  "轻松月入",
  "保证赚钱",
  "包赚",
  "只赚不赔",
  "暴利项目",
  "拉人头"
];

// Top 15 anxiety/clickbait phrases (from _ANXIETY_PHRASES in rules.py)
const ANXIETY_PHRASES = [
  "再不.*就晚了",
  "99%的人不知道",
  "震惊",
  "必看",
  "紧急",
  "全网疯传",
  "错过就没了",
  "最后机会",
  "不看后悔",
  "手慢无",
  "揭秘",
  "惊人发现",
  "万万没想到",
  "细思极恐",
  "删前速看"
];

// Top 15 advertorial/commercial keywords (from _ADVERTORIAL_KEYWORDS in rules.py)
const ADVERTORIAL_KEYWORDS = [
  "推荐码",
  "优惠券",
  "折扣码",
  "点击链接",
  "复制口令",
  "返利",
  "佣金",
  "分销",
  "带货",
  "种草",
  "好物推荐",
  "安利",
  "亲测有效",
  "良心推荐",
  "粉丝专属"
];

/**
 * Count keyword matches in text for a given keyword list.
 * Supports regex patterns (strings containing regex special chars).
 * @param {string} text - The text to scan.
 * @param {string[]} keywords - List of keywords or regex patterns.
 * @returns {{count: number, matched: string[]}}
 */
function countMatches(text, keywords) {
  const matched = [];
  let count = 0;
  for (const kw of keywords) {
    try {
      const regex = new RegExp(kw);
      if (regex.test(text)) {
        count++;
        matched.push(kw);
      }
    } catch (e) {
      // Fallback to simple string matching if regex fails
      if (text.includes(kw)) {
        count++;
        matched.push(kw);
      }
    }
  }
  return { count, matched };
}

/**
 * Score content text using local keyword rules.
 *
 * @param {string} text - Article body text to analyze.
 * @returns {{score: number, verdict: string, matchedKeywords: string[], explanation: string}}
 *   score: 0 (clean) to 100 (junk)
 *   verdict: 'quality' | 'suspicious' | 'junk'
 *   matchedKeywords: array of matched keyword strings
 *   explanation: one-line Chinese explanation
 */
function scoreContent(text) {
  if (!text || text.trim().length === 0) {
    return {
      score: 0,
      verdict: "quality",
      matchedKeywords: [],
      explanation: "\u2705 \u65e0\u5185\u5bb9\u53ef\u5206\u6790"
    };
  }

  const scamResult = countMatches(text, SCAM_KEYWORDS);
  const anxietyResult = countMatches(text, ANXIETY_PHRASES);
  const advertorialResult = countMatches(text, ADVERTORIAL_KEYWORDS);

  const allMatched = [
    ...scamResult.matched,
    ...anxietyResult.matched,
    ...advertorialResult.matched
  ];

  // Compute risk score based on weighted hit counts
  // Scam keywords are most impactful (weight 15 per hit, capped contribution 60)
  // Anxiety phrases (weight 10 per hit, capped contribution 30)
  // Advertorial keywords (weight 8 per hit, capped contribution 30)
  const scamScore = Math.min(scamResult.count * 15, 60);
  const anxietyScore = Math.min(anxietyResult.count * 10, 30);
  const advertorialScore = Math.min(advertorialResult.count * 8, 30);

  const rawScore = scamScore + anxietyScore + advertorialScore;
  const score = Math.min(rawScore, 100);

  // Determine verdict
  let verdict;
  if (score >= 60) {
    verdict = "junk";
  } else if (score >= 30) {
    verdict = "suspicious";
  } else {
    verdict = "quality";
  }

  // Generate Chinese explanation
  const explanation = generateExplanation(
    verdict,
    score,
    scamResult,
    anxietyResult,
    advertorialResult
  );

  return { score, verdict, matchedKeywords: allMatched, explanation };
}

/**
 * Generate a one-line Chinese explanation of the scoring result.
 */
function generateExplanation(verdict, score, scamResult, anxietyResult, advertorialResult) {
  if (verdict === "quality") {
    return "\u2705 \u5185\u5bb9\u8d28\u91cf\u6b63\u5e38\uff0c\u672a\u53d1\u73b0\u660e\u663e\u95ee\u9898\u3002";
  }

  const parts = [];

  if (scamResult.count > 0) {
    const examples = scamResult.matched.slice(0, 2).map(k => `\u201c${k}\u201d`).join("");
    parts.push(`${scamResult.count} \u5904\u8bc8\u9a97\u5173\u952e\u8bcd\uff08${examples}\uff09`);
  }

  if (anxietyResult.count > 0) {
    const examples = anxietyResult.matched.slice(0, 2).map(k => `\u201c${k}\u201d`).join("");
    parts.push(`${anxietyResult.count} \u5904\u7126\u8651\u8425\u9500\u8bcd\uff08${examples}\uff09`);
  }

  if (advertorialResult.count > 0) {
    const examples = advertorialResult.matched.slice(0, 2).map(k => `\u201c${k}\u201d`).join("");
    parts.push(`${advertorialResult.count} \u5904\u5e7f\u544a\u63a8\u5e7f\u8bcd\uff08${examples}\uff09`);
  }

  const prefix = verdict === "junk" ? "\ud83d\udea8 \u9ad8\u98ce\u9669\u5185\u5bb9\u3002" : "\u26a0\ufe0f \u5185\u5bb9\u53ef\u7591\u3002";
  return `${prefix}\u53d1\u73b0${parts.join("\u3001")}\u3002`;
}

// Export for use in background.js (via importScripts) and tests
if (typeof module !== "undefined" && module.exports) {
  module.exports = { scoreContent, SCAM_KEYWORDS, ANXIETY_PHRASES, ADVERTORIAL_KEYWORDS };
}
