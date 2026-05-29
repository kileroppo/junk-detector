/**
 * background.js - Service worker for the Chrome extension.
 *
 * Receives content from content scripts, scores it using the rules engine,
 * updates the badge, and stores results for the popup.
 */

// Import rules.js scoring logic into the service worker
importScripts("rules.js");

// Session cache for URL results to avoid re-scoring on back navigation
const resultCache = new Map();

/**
 * Badge symbols for each verdict (replaces numeric score).
 */
const BADGE_SYMBOLS = {
  quality: "\u2713",
  suspicious: "!",
  junk: "\u2717"
};

/**
 * Update the extension badge with symbol and appropriate color.
 * Includes a brief blink animation for attention.
 * @param {number} tabId
 * @param {{score: number, verdict: string}} result
 */
function updateBadge(tabId, result) {
  const colors = {
    quality: "#34C759",
    suspicious: "#FF9500",
    junk: "#FF3B30"
  };

  const badgeText = BADGE_SYMBOLS[result.verdict] || "";
  const badgeColor = colors[result.verdict] || "#999999";

  chrome.action.setBadgeText({ text: badgeText, tabId: tabId });
  chrome.action.setBadgeBackgroundColor({ color: badgeColor, tabId: tabId });

  // Brief blink animation: clear then restore
  setTimeout(function () {
    chrome.action.setBadgeText({ text: "", tabId: tabId });
    setTimeout(function () {
      chrome.action.setBadgeText({ text: badgeText, tabId: tabId });
    }, 200);
  }, 100);
}

/**
 * Set the action icon based on the content verdict.
 * Uses eye-themed SVG icons to represent content quality state.
 * @param {number} tabId
 * @param {string} verdict - 'quality', 'suspicious', or 'junk'
 */
function updateActionIcon(tabId, verdict) {
  const iconPaths = {
    quality: "icons/eye-green.svg",
    suspicious: "icons/eye-amber.svg",
    junk: "icons/eye-red.svg"
  };

  const iconPath = iconPaths[verdict] || "icons/eye-green.svg";
  chrome.action.setIcon({ path: iconPath, tabId: tabId });
}

/**
 * Store the latest result for the popup to read.
 * @param {number} tabId
 * @param {object} result
 */
function storeResult(tabId, result) {
  const data = {};
  data["result_" + tabId] = result;
  chrome.storage.local.set(data);
}

/**
 * Push a scoring entry to the history array (keeps last 5 entries).
 * @param {object} tab - The Chrome tab object
 * @param {object} result - The scoring result
 */
function pushToHistory(tab, result) {
  chrome.storage.local.get("history", function (data) {
    var history = data["history"] || [];
    history.push({
      title: tab.title || "",
      verdict: result.verdict,
      url: tab.url || "",
      timestamp: Date.now()
    });
    // Keep only last 5
    if (history.length > 5) {
      history = history.slice(history.length - 5);
    }
    chrome.storage.local.set({ history: history });
  });
}

/**
 * Increment daily stats counters.
 * Key format: stats_YYYY-MM-DD
 * Value: {total: N, quality: N, suspicious: N, junk: N}
 * Also tracks consecutive days in 'streak' key.
 * @param {string} verdict - 'quality', 'suspicious', or 'junk'
 */
function incrementDailyStats(verdict) {
  var today = new Date().toISOString().slice(0, 10);
  var statsKey = "stats_" + today;
  chrome.storage.local.get([statsKey, "streak", "last_active_date"], function (data) {
    var stats = data[statsKey] || { total: 0, quality: 0, suspicious: 0, junk: 0 };
    stats.total += 1;
    if (verdict === "quality" || verdict === "suspicious" || verdict === "junk") {
      stats[verdict] += 1;
    }

    var updates = {};
    updates[statsKey] = stats;

    // Update streak
    var lastDate = data["last_active_date"] || "";
    var streak = data["streak"] || 0;
    if (lastDate !== today) {
      // Check if yesterday was active
      var yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      if (lastDate === yesterday) {
        streak += 1;
      } else if (lastDate === "") {
        streak = 1;
      } else {
        streak = 1; // Reset streak
      }
      updates["last_active_date"] = today;
      updates["streak"] = streak;
    }

    chrome.storage.local.set(updates);
  });
}

/**
 * Increment the global score count for social proof display.
 * Stored in chrome.storage.local under 'global_score_count'.
 */
function incrementGlobalScoreCount() {
  chrome.storage.local.get("global_score_count", function (data) {
    var count = (data["global_score_count"] || 0) + 1;
    chrome.storage.local.set({ global_score_count: count });
  });
}

/**
 * Update personal calibration based on user behavior.
 * Tracks dismiss_count and feedback_count.
 */
function updateCalibration(type) {
  chrome.storage.local.get("calibration", function (data) {
    var calibration = data.calibration || {
      dismiss_count: 0,
      feedback_count: 0,
      sensitivity_adjustment: 0
    };

    if (type === "dismiss") {
      calibration.dismiss_count += 1;
      // When dismiss_count > 5, auto-increase threshold (more lenient)
      if (calibration.dismiss_count > 5) {
        calibration.sensitivity_adjustment = 5;
      }
    } else if (type === "feedback") {
      calibration.feedback_count += 1;
      // When feedback > 3, increase sensitivity
      if (calibration.feedback_count > 3) {
        calibration.sensitivity_adjustment = -5;
      }
    }

    chrome.storage.local.set({ calibration: calibration });
  });
}

/**
 * Apply calibration adjustment to scoring result.
 * @param {object} result - The raw scoring result
 * @param {function} callback - Called with adjusted result
 */
function applyCalibration(result, callback) {
  chrome.storage.local.get("calibration", function (data) {
    var calibration = data.calibration || { sensitivity_adjustment: 0 };
    var adjustment = calibration.sensitivity_adjustment || 0;

    if (adjustment !== 0) {
      // Adjust the score: positive adjustment means more lenient (lower score)
      var adjustedScore = Math.max(0, Math.min(100, result.score - adjustment));
      result.score = adjustedScore;

      // Recalculate verdict based on adjusted score
      if (adjustedScore >= 60) {
        result.verdict = "junk";
      } else if (adjustedScore >= 30) {
        result.verdict = "suspicious";
      } else {
        result.verdict = "quality";
      }
    }

    callback(result);
  });
}

/**
 * Check if sound is enabled and play alert for junk verdict.
 * @param {string} verdict
 */
function checkSoundAlert(verdict) {
  if (verdict !== "junk") return;
  chrome.storage.sync.get("sound_enabled", function (data) {
    if (data.sound_enabled) {
      // Use chrome.notifications API for audio alert
      chrome.notifications.create("junk-alert-" + Date.now(), {
        type: "basic",
        iconUrl: "icons/icon-gray-128.png",
        title: "\u9274\u771f\u8b66\u544a",
        message: "\u68c0\u6d4b\u5230\u9ad8\u98ce\u9669\u5185\u5bb9",
        silent: false
      });
    }
  });
}

/**
 * Update top sites tracking data after scoring.
 * @param {string} url - The tab URL
 * @param {object} result - The scoring result
 */
function updateTopSites(url, result) {
  if (!url) return;
  try {
    var domain = new URL(url).hostname;
    chrome.storage.local.get("top_sites", function (data) {
      var sites = data.top_sites || {};
      if (!sites[domain]) sites[domain] = { count: 0, totalScore: 0 };
      sites[domain].count += 1;
      sites[domain].totalScore += (100 - result.score);
      // Cap at 50 domains: remove the domain with lowest count
      var keys = Object.keys(sites);
      if (keys.length > 50) {
        var minDomain = null;
        var minCount = Infinity;
        for (var i = 0; i < keys.length; i++) {
          if (sites[keys[i]].count < minCount) {
            minCount = sites[keys[i]].count;
            minDomain = keys[i];
          }
        }
        if (minDomain) {
          delete sites[minDomain];
        }
      }
      chrome.storage.local.set({ top_sites: sites });
    });
  } catch (e) {
    // Invalid URL, skip
  }
}

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (message.type === "SCORE_CONTENT" && message.text) {
    const tabId = sender.tab ? sender.tab.id : null;
    const tabUrl = sender.tab ? sender.tab.url : null;

    // Check cache first
    if (tabUrl && resultCache.has(tabUrl)) {
      var cachedResult = resultCache.get(tabUrl);
      if (tabId) {
        updateBadge(tabId, cachedResult);
        updateActionIcon(tabId, cachedResult.verdict);
        storeResult(tabId, cachedResult);
      }
      sendResponse({ result: cachedResult });
      return true;
    }

    // Read custom keywords from storage, then score
    chrome.storage.sync.get("custom_keywords", function (kwData) {
      var customKeywords = [];
      if (kwData.custom_keywords && typeof kwData.custom_keywords === "string") {
        customKeywords = kwData.custom_keywords.split("\n").map(function (s) { return s.trim(); }).filter(function (s) { return s.length > 0; });
      }

      var rawResult = scoreContent(message.text, { customKeywords: customKeywords });

      // Apply calibration adjustment
      applyCalibration(rawResult, function (result) {
        // Cache the result by URL
        if (tabUrl) {
          resultCache.set(tabUrl, result);
        }

        if (tabId) {
          updateBadge(tabId, result);
          updateActionIcon(tabId, result.verdict);
          storeResult(tabId, result);
          if (sender.tab) {
            pushToHistory(sender.tab, result);
          }
          incrementDailyStats(result.verdict);
          incrementGlobalScoreCount();
          checkSoundAlert(result.verdict);
          updateTopSites(tabUrl, result);
        }

        sendResponse({ result: result });
      });
    });
  } else if (message.type === "DISMISS_URL") {
    // Track dismiss for calibration
    updateCalibration("dismiss");
    sendResponse({ ok: true });
  } else if (message.type === "USER_FEEDBACK") {
    // Track feedback for calibration
    updateCalibration("feedback");
    sendResponse({ ok: true });
  }
  // Return true to indicate async response
  return true;
});

// Clear cache on tab navigation (reload or new URL)
chrome.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
  if (changeInfo.status === "loading" && tab.url) {
    resultCache.delete(tab.url);
  }
});

// Clear stored results when a tab is closed
chrome.tabs.onRemoved.addListener(function (tabId) {
  chrome.storage.local.remove("result_" + tabId);
});

// Open onboarding page on first install and create context menus
chrome.runtime.onInstalled.addListener(function (details) {
  if (details.reason === "install") {
    chrome.tabs.create({ url: "onboarding.html" });
  } else if (details.reason === "update") {
    // Store update flag for popup to show
    chrome.storage.local.set({
      updated: true,
      previousVersion: details.previousVersion
    });
  }

  // Create whitelist context menu item
  chrome.contextMenus.create({
    id: "trust-site",
    title: "\u4fe1\u4efb\u6b64\u7f51\u7ad9\uff08\u4e0d\u518d\u68c0\u6d4b\uff09",
    contexts: ["page"]
  });

  // Create selection scoring context menu item
  chrome.contextMenus.create({
    id: "score-selection",
    title: "\u7528\u9274\u771f\u68c0\u6d4b\u9009\u4e2d\u7684\u6587\u5b57",
    contexts: ["selection"]
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener(function (info, tab) {
  if (info.menuItemId === "trust-site" && tab && tab.url) {
    var domain = new URL(tab.url).hostname;
    chrome.storage.sync.get("whitelist", function (data) {
      var whitelist = data.whitelist || [];
      if (!whitelist.includes(domain)) {
        whitelist.push(domain);
        chrome.storage.sync.set({ whitelist: whitelist });
      }
    });
  } else if (info.menuItemId === "score-selection" && info.selectionText) {
    // Score the selected text
    var result = scoreContent(info.selectionText);
    // Store result for popup to read
    if (tab && tab.id) {
      storeResult(tab.id, result);
      updateBadge(tab.id, result);
      updateActionIcon(tab.id, result.verdict);
    }
  }
});
