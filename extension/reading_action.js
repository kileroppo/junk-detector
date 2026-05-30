/**
 * reading_action.js — verdict-first display (aligned with web result_display).
 * Port of src/core/content_genre.py + reading_action mapping (rules-only).
 */
(function (global) {
  "use strict";

  var READING_ACTIONS = {
    skip: { label: "建议跳过", emoji: "\ud83d\udeab", css: "reading-action--skip" },
    skim: { label: "速查即可", emoji: "\ud83d\udccb", css: "reading-action--skim" },
    read: { label: "值得细读", emoji: "\u2713", css: "reading-action--read" },
    verify: { label: "谨慎核实", emoji: "\u26a0", css: "reading-action--verify" }
  };

  var GENRE_DISPLAY = {
    roundup: { label: "工具清单", icon: "\ud83d\udcda" },
    opinion: { label: "观点评论", icon: "\ud83d\udcad" },
    news: { label: "资讯报道", icon: "\ud83d\udcf0" },
    advertorial: { label: "商业推广", icon: "\ud83d\uded2" },
    default: { label: "", icon: "" }
  };

  var INSTALL_MARKERS = [
    "npx skills add",
    "plugin marketplace",
    "claude plugin add",
    "/plugin marketplace",
    "skills add",
    "marketplace add",
    "plugin add"
  ];

  function countRegex(text, pattern) {
    var m = text.match(pattern);
    return m ? m.length : 0;
  }

  function detectContentGenre(text) {
    if (!text || text.trim().length < 200) {
      return "default";
    }
    var lower = text.toLowerCase();
    var scamHits = 0;
    if (typeof SCAM_KEYWORDS !== "undefined") {
      for (var i = 0; i < SCAM_KEYWORDS.length; i++) {
        if (text.indexOf(SCAM_KEYWORDS[i]) !== -1) {
          scamHits++;
        }
      }
    }
    if (scamHits >= 2) {
      return "advertorial";
    }
    var adHits = 0;
    if (typeof ADVERTORIAL_KEYWORDS !== "undefined") {
      for (var j = 0; j < ADVERTORIAL_KEYWORDS.length; j++) {
        if (text.indexOf(ADVERTORIAL_KEYWORDS[j]) !== -1) {
          adHits++;
        }
      }
    }
    if (adHits >= 3) {
      return "advertorial";
    }
    if (/据悉|记者|本报讯|新华社|报道称/.test(text) && /(?:\d{1,2}月\d{1,2}日|今天|昨日)/.test(text)) {
      return "news";
    }
    if (/(我认为|在我看来|笔者认为|个人观点|深度分析)/.test(text)) {
      return "opinion";
    }
    var signals = 0;
    if (countRegex(text, /^\s*\d+[\.\)、]/gm) >= 4) {
      signals++;
    }
    if (countRegex(text, /github\.com/gi) >= 2) {
      signals++;
    }
    var installs = 0;
    for (var k = 0; k < INSTALL_MARKERS.length; k++) {
      if (lower.indexOf(INSTALL_MARKERS[k]) !== -1) {
        installs++;
      }
    }
    if (installs >= 1) {
      signals++;
    }
    if (/对比表/.test(text) || /\|\s*Skill\s*\|/i.test(text)) {
      signals++;
    }
    if (/(完整指南|选型|哪款|清单|盘点|合集|最佳\s*\d+)/.test(text)) {
      signals++;
    }
    return signals >= 2 ? "roundup" : "default";
  }

  function computeReferenceValueScore(text) {
    if (!text) {
      return 0;
    }
    var score = 28;
    score += Math.min(28, countRegex(text, /github\.com/gi) * 2.5);
    score += Math.min(18, countRegex(text, /^\s*\d+[\.\)、]/gm) * 1.8);
    var installs = 0;
    var lower = text.toLowerCase();
    for (var i = 0; i < INSTALL_MARKERS.length; i++) {
      if (lower.indexOf(INSTALL_MARKERS[i]) !== -1) {
        installs++;
      }
    }
    score += Math.min(14, installs * 5);
    if (/对比表/.test(text) || /\|\s*Skill\s*\|/i.test(text)) {
      score += 12;
    }
    if (/(仓库|安装|stars|star\)|插件)/i.test(text)) {
      score += 6;
    }
    return Math.round(Math.max(0, Math.min(100, score)) * 10) / 10;
  }

  function scoreTierFromQuality(qualityScore, genre) {
    if (genre === "roundup" && qualityScore >= 32 && qualityScore < 60) {
      return { key: "reference", label: "汇编参考" };
    }
    if (qualityScore >= 80) {
      return { key: "quality", label: "质量良好" };
    }
    if (qualityScore >= 60) {
      return { key: "normal", label: "整体一般" };
    }
    if (qualityScore >= 40) {
      return { key: "suspicious", label: "需谨慎" };
    }
    return { key: "junk", label: "高风险" };
  }

  function buildReadingAction(result, genre, text) {
    var quality = 100 - (result.score || 0);
    var tier = scoreTierFromQuality(quality, genre);
    var key = "skim";
    if (result.verdict === "junk") {
      key = "skip";
    } else if (genre === "roundup" && quality >= 32 && result.verdict !== "junk") {
      key = "skim";
    } else if (result.verdict === "quality") {
      key = "read";
    } else if (result.verdict === "suspicious") {
      key = tier.key === "junk" ? "skip" : "verify";
    }
    if (result.severity === "danger") {
      key = "skip";
    }
    var action = {};
    var base = READING_ACTIONS[key];
    for (var prop in base) {
      if (Object.prototype.hasOwnProperty.call(base, prop)) {
        action[prop] = base[prop];
      }
    }
    action.key = key;
    action.tier_label = tier.label;
    return action;
  }

  function enrichScoringResult(result, text) {
    var genre = detectContentGenre(text || "");
    var referenceValue = genre === "roundup" ? computeReferenceValueScore(text) : null;
    var readingAction = buildReadingAction(result, genre, text);
    result.content_genre = genre;
    result.reading_action = readingAction;
    result.reference_value = referenceValue;
    result.genre_display = GENRE_DISPLAY[genre] || GENRE_DISPLAY.default;
    return result;
  }

  global.READING_ACTIONS = READING_ACTIONS;
  global.GENRE_DISPLAY = GENRE_DISPLAY;
  global.detectContentGenre = detectContentGenre;
  global.computeReferenceValueScore = computeReferenceValueScore;
  global.buildReadingAction = buildReadingAction;
  global.enrichScoringResult = enrichScoringResult;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      READING_ACTIONS: READING_ACTIONS,
      GENRE_DISPLAY: GENRE_DISPLAY,
      detectContentGenre: detectContentGenre,
      computeReferenceValueScore: computeReferenceValueScore,
      buildReadingAction: buildReadingAction,
      enrichScoringResult: enrichScoringResult
    };
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
