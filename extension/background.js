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
 * Store the latest result for the popup to read.
 * @param {number} tabId
 * @param {object} result
 */
function storeResult(tabId, result) {
  const data = {};
  data["result_" + tabId] = result;
  chrome.storage.local.set(data);
}

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
  if (message.type === "SCORE_CONTENT" && message.text) {
    const result = scoreContent(message.text);
    const tabId = sender.tab ? sender.tab.id : null;

    if (tabId) {
      updateBadge(tabId, result);
      storeResult(tabId, result);
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
