/**
 * background.js - Service worker for the Chrome extension.
 *
 * Receives content from content scripts, scores it using the rules engine,
 * updates the badge, and stores results for the popup.
 */

// Import rules.js scoring logic into the service worker
importScripts("rules.js");

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
    const result = scoreContent(message.text);
    const tabId = sender.tab ? sender.tab.id : null;

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

// Clear stored results when a tab is closed
chrome.tabs.onRemoved.addListener(function (tabId) {
  chrome.storage.local.remove("result_" + tabId);
});

// Open onboarding page on first install
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
});
