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
 * @param {object} [options] - Optional settings.
 * @param {string} [options.sensitivity] - 'strict', 'standard', or 'relaxed'.
 * @returns {{score: number, verdict: string, matchedKeywords: string[], explanation: string}}
 *   score: 0 (clean) to 100 (junk)
 *   verdict: 'quality' | 'suspicious' | 'junk'
 *   matchedKeywords: array of matched keyword strings
 *   explanation: one-line Chinese explanation
 */
function scoreContent(text, options) {
  if (!text || text.trim().length === 0) {
    return {
      score: 0,
      verdict: "quality",
      matchedKeywords: [],
      explanation: "\u2705 \u65e0\u5185\u5bb9\u53ef\u5206\u6790"
    };
  }

  var sensitivity = (options && options.sensitivity) || "standard";
  // Threshold for junk verdict based on sensitivity
  var junkThreshold = 60;
  var suspiciousThreshold = 30;
  if (sensitivity === "strict") {
    junkThreshold = 50;
    suspiciousThreshold = 20;
  } else if (sensitivity === "relaxed") {
    junkThreshold = 75;
    suspiciousThreshold = 40;
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
  let explanation;
  if (score >= junkThreshold) {
    verdict = "junk";
  } else if (score >= 25 && score < 45) {
    // Low confidence zone - honest uncertainty
    verdict = "suspicious";
    explanation = "\ud83e\udd14 \u4e0d\u592a\u786e\u5b9a\u3002\u53d1\u73b0\u4e00\u4e9b\u53ef\u7591\u4fe1\u53f7\u4f46\u4e0d\u8db3\u4ee5\u4e0b\u7ed3\u8bba\u3002\u5efa\u8bae\u8c28\u614e\u9605\u8bfb\u3002";
  } else if (score >= suspiciousThreshold) {
    verdict = "suspicious";
  } else {
    verdict = "quality";
  }

  // Generate Chinese explanation (only if not already set by uncertainty handler)
  if (!explanation) {
    explanation = generateExplanation(
      verdict,
      score,
      scamResult,
      anxietyResult,
      advertorialResult
    );
  }

  return { score, verdict, matchedKeywords: allMatched, explanation };
}

/**
 * Generate a simple numeric hash from a string for deterministic template selection.
 * @param {string} str
 * @returns {number} Non-negative integer hash
 */
function simpleStringHash(str) {
  var hash = 0;
  for (var i = 0; i < str.length; i++) {
    var char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

/**
 * Generate a one-line Chinese explanation of the scoring result.
 * Uses varied sentence structures for natural-sounding output.
 * Template selection is deterministic per content (hash-based).
 */
function generateExplanation(verdict, score, scamResult, anxietyResult, advertorialResult) {
  // Build a seed string from matched keywords for deterministic selection
  var allMatched = [].concat(scamResult.matched, anxietyResult.matched, advertorialResult.matched);
  var seedStr = verdict + ":" + score + ":" + allMatched.join(",");
  var hashVal = simpleStringHash(seedStr);

  if (verdict === "quality") {
    var qualityTemplates = [
      "\u2705 \u5185\u5bb9\u8d28\u91cf\u6b63\u5e38\uff0c\u672a\u53d1\u73b0\u660e\u663e\u95ee\u9898\u3002",
      "\u2705 \u672a\u68c0\u6d4b\u5230\u5783\u573e\u4fe1\u606f\u7279\u5f81\uff0c\u5185\u5bb9\u53ef\u4fe1\u3002",
      "\u2705 \u89c4\u5219\u5f15\u64ce\u672a\u53d1\u73b0\u98ce\u9669\u4fe1\u53f7\uff0c\u9605\u8bfb\u65e0\u865e\u3002"
    ];
    return qualityTemplates[hashVal % qualityTemplates.length];
  }

  var parts = [];

  if (scamResult.count > 0) {
    var examples = scamResult.matched.slice(0, 2).map(function(k) { return "\u201c" + k + "\u201d"; }).join("\u3001");
    var scamTemplates = [
      "\u542b\u6709\u5178\u578b\u8bc8\u9a97\u8bdd\u672f\uff1a" + examples,
      "\u53d1\u73b0 " + scamResult.count + " \u5904\u6295\u8d44\u8bf1\u5bfc\u7528\u8bed\uff08" + examples + "\uff09",
      "\u591a\u5904\u8bc8\u9a97\u5173\u952e\u8bcd\uff1a" + examples
    ];
    parts.push(scamTemplates[hashVal % scamTemplates.length]);
  }

  if (anxietyResult.count > 0) {
    var examples = anxietyResult.matched.slice(0, 2).map(function(k) { return "\u201c" + k + "\u201d"; }).join("\u3001");
    var anxietyTemplates = [
      "\u9891\u7e41\u4f7f\u7528\u9650\u65f6\u7d27\u8feb\u8bdd\u672f\uff1a" + examples,
      "\u542b\u6709 " + anxietyResult.count + " \u5904\u7126\u8651\u8425\u9500\u8bcd\uff08" + examples + "\uff09",
      "\u5229\u7528\u60c5\u7eea\u64cd\u63a7\u8bfb\u8005\uff1a" + examples
    ];
    parts.push(anxietyTemplates[hashVal % anxietyTemplates.length]);
  }

  if (advertorialResult.count > 0) {
    var examples = advertorialResult.matched.slice(0, 2).map(function(k) { return "\u201c" + k + "\u201d"; }).join("\u3001");
    var advertorialTemplates = [
      "\u7591\u4f3c\u5e26\u8d27\u63a8\u5e7f\uff1a" + examples,
      "\u68c0\u6d4b\u5230\u5546\u4e1a\u63a8\u5e7f\u8bcd\u6c47\uff1a" + examples,
      "\u542b\u6709 " + advertorialResult.count + " \u5904\u5e7f\u544a\u5f15\u5bfc\u7528\u8bed\uff08" + examples + "\uff09"
    ];
    parts.push(advertorialTemplates[hashVal % advertorialTemplates.length]);
  }

  var prefix = verdict === "junk" ? "\ud83d\udea8 \u9ad8\u98ce\u9669\u5185\u5bb9\u3002" : "\u26a0\ufe0f \u5185\u5bb9\u53ef\u7591\u3002";
  return prefix + parts.join("\uff1b") + "\u3002";
}

/**
 * Educational explanations for manipulation keywords.
 * Maps keywords to Chinese explanations of the manipulation technique used.
 */
const KEYWORD_EXPLANATIONS = {
  "日入过万": "夸大收益承诺是典型诈骗话术，真实投资回报不可能如此确定",
  "限时免费": "制造虚假紧迫感，迫使你不经思考就行动",
  "加微信": "诱导私聊以脱离平台监管，是诈骗转化的常见手段",
  "躺赚": "暗示不劳而获，利用贪婪心理诱导上钩",
  "财富自由": "用模糊的成功愿景吸引注意力，缺乏具体可验证的承诺",
  "零成本": "不存在真正的零成本项目，隐藏的代价往往更高",
  "稳赚不赔": "任何投资都有风险，承诺无风险是典型骗局特征",
  "名额有限": "人为制造稀缺感，压缩你的决策时间",
  "震惊": "使用情绪化标题吸引点击，内容往往与标题不符",
  "99%的人不知道": "虚假的信息独占感，让你觉得获得了特殊知识",
  "再不.*就晚了": "利用错失恐惧心理操纵读者情绪",
  "推荐码": "隐性商业推广，作者从你的购买中获得佣金",
  "亲测有效": "伪装成个人体验的广告话术，可信度需要验证",
  "月入百万": "极端收益承诺，远超正常商业回报的虚假宣传",
  "免费领取": "以免费为诱饵获取你的个人信息或后续付费"
};

// Export for use in background.js (via importScripts) and tests
if (typeof module !== "undefined" && module.exports) {
  module.exports = { scoreContent, simpleStringHash, SCAM_KEYWORDS, ANXIETY_PHRASES, ADVERTORIAL_KEYWORDS, KEYWORD_EXPLANATIONS };
}
