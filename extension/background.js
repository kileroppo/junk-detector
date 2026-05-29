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
 * Update the extension badge with the score and appropriate color.
 * @param {number} tabId
 * @param {{score: number, verdict: string}} result
 */
function updateBadge(tabId, result) {
  const colors = {
    quality: "#34C759",
    suspicious: "#FF9500",
    junk: "#FF3B30"
  };

  const badgeText = result.score > 0 ? String(result.score) : "";
  const badgeColor = colors[result.verdict] || "#999999";

  chrome.action.setBadgeText({ text: badgeText, tabId: tabId });
  chrome.action.setBadgeBackgroundColor({ color: badgeColor, tabId: tabId });
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

    const result = scoreContent(message.text);

    // Cache the result by URL
    if (tabUrl) {
      resultCache.set(tabUrl, result);
    }

    if (tabId) {
      updateBadge(tabId, result);
      updateActionIcon(tabId, result.verdict);
      storeResult(tabId, result);
      pushToHistory(sender.tab, result);
      incrementDailyStats(result.verdict);
    }

    sendResponse({ result: result });
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

// Open onboarding page on first install and create context menu
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
});

// Handle context menu clicks for whitelisting
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
  }
});
