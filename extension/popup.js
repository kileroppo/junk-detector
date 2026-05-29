/**
 * popup.js - Popup UI logic for the Chrome extension.
 *
 * Reads the latest scoring result from chrome.storage.local and displays it.
 * Features: hamburger menu, dismiss, keyboard shortcuts, offline mode,
 * smooth loading, alternative suggestions.
 */

(function () {
  "use strict";

  const VERDICT_ICONS = {
    quality: "\u2705",
    suspicious: "\u26a0\ufe0f",
    junk: "\ud83d\udea8"
  };

  /**
   * Check if the browser is offline and show the badge.
   */
  function checkOffline() {
    const badge = document.getElementById("offline-badge");
    if (!navigator.onLine) {
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  /**
   * Setup hamburger menu toggle.
   */
  function setupHamburgerMenu() {
    const btn = document.getElementById("hamburger-btn");
    const panel = document.getElementById("menu-panel");
    btn.addEventListener("click", function () {
      panel.classList.toggle("hidden");
      btn.classList.toggle("active");
    });
  }

  /**
   * Show alternative search links for suspicious/junk content.
   * @param {string} title - The page title to search for
   * @param {string} verdict - The verdict result
   */
  function showAlternatives(title, verdict) {
    const section = document.getElementById("alternatives-section");
    const linksEl = document.getElementById("alternatives-links");

    if (verdict !== "suspicious" && verdict !== "junk") {
      section.classList.add("hidden");
      return;
    }

    if (!title || title.trim().length === 0) {
      section.classList.add("hidden");
      return;
    }

    const query = encodeURIComponent(title.trim());
    linksEl.innerHTML = "";

    const zhihuLink = document.createElement("a");
    zhihuLink.href = "https://www.zhihu.com/search?type=content&q=" + query;
    zhihuLink.textContent = "\u5728\u77e5\u4e4e\u641c\u7d22";
    zhihuLink.target = "_blank";

    const googleLink = document.createElement("a");
    googleLink.href = "https://www.google.com/search?q=" + query;
    googleLink.textContent = "\u5728Google\u641c\u7d22";
    googleLink.target = "_blank";

    linksEl.appendChild(zhihuLink);
    linksEl.appendChild(googleLink);
    section.classList.remove("hidden");
  }

  /**
   * Setup dismiss button click handler.
   * Stores {url, timestamp} in chrome.storage.local under 'dismissals'.
   */
  function setupDismissButton() {
    const dismissBtn = document.getElementById("dismiss-btn");
    dismissBtn.addEventListener("click", function () {
      chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        if (!tabs || tabs.length === 0) return;
        const url = tabs[0].url || "";
        chrome.storage.local.get("dismissals", function (data) {
          const dismissals = data.dismissals || [];
          dismissals.push({ url: url, timestamp: Date.now() });
          chrome.storage.local.set({ dismissals: dismissals }, function () {
            dismissBtn.textContent = "\u5df2\u5ffd\u7565";
            dismissBtn.disabled = true;
            dismissBtn.style.opacity = "0.5";
          });
        });
      });
    });
  }

  /**
   * Update the popup UI with scoring results.
   * @param {object|null} result
   * @param {string|null} pageTitle - Title of the active tab
   */
  function displayResult(result, pageTitle) {
    const iconEl = document.getElementById("verdict-icon");
    const explanationEl = document.getElementById("explanation");
    const scoreEl = document.getElementById("score-value");
    const keywordsEl = document.getElementById("keywords-list");
    const dailyStatsEl = document.getElementById("daily-stats");
    const dismissBtn = document.getElementById("dismiss-btn");

    if (!result) {
      iconEl.textContent = "\u2753";
      explanationEl.textContent = "\u8bf7\u5728\u652f\u6301\u7684\u7f51\u7ad9\u4e0a\u6253\u5f00\u6587\u7ae0\u540e\u518d\u68c0\u6d4b";
      scoreEl.textContent = "--";
      scoreEl.className = "score-value";
      dismissBtn.classList.add("hidden");
      document.getElementById("alternatives-section").classList.add("hidden");
      // Show daily stats when no active result
      showDailyStats(dailyStatsEl);
      return;
    }

    // Hide daily stats when there is an active result
    dailyStatsEl.classList.add("hidden");

    iconEl.textContent = VERDICT_ICONS[result.verdict] || "\u2753";
    explanationEl.textContent = result.explanation || "";

    // Show dismiss button for suspicious/junk verdicts
    if (result.verdict === "suspicious" || result.verdict === "junk") {
      dismissBtn.classList.remove("hidden");
    } else {
      dismissBtn.classList.add("hidden");
    }

    // Show alternative suggestions for suspicious/junk
    showAlternatives(pageTitle, result.verdict);

    // Invert score: display as quality score (100 = best, 0 = worst)
    var qualityScore = 100 - (result.score || 0);
    scoreEl.textContent = String(qualityScore);
    scoreEl.className = "score-value " + result.verdict;

    // Render matched keywords
    keywordsEl.innerHTML = "";
    if (result.matchedKeywords && result.matchedKeywords.length > 0) {
      result.matchedKeywords.forEach(function (kw) {
        const tag = document.createElement("span");
        tag.className = "keyword-tag";
        tag.textContent = kw;
        keywordsEl.appendChild(tag);
      });

      // Show educational explanations section
      var whySection = document.getElementById("why-section");
      var whyContent = document.getElementById("why-content");
      var hasExplanations = false;

      whyContent.innerHTML = "";
      result.matchedKeywords.forEach(function (kw) {
        if (typeof KEYWORD_EXPLANATIONS !== "undefined" && KEYWORD_EXPLANATIONS[kw]) {
          hasExplanations = true;
          var item = document.createElement("div");
          item.className = "why-item";
          var kwEl = document.createElement("div");
          kwEl.className = "why-keyword";
          kwEl.textContent = kw;
          var expEl = document.createElement("div");
          expEl.className = "why-explanation";
          expEl.textContent = KEYWORD_EXPLANATIONS[kw];
          item.appendChild(kwEl);
          item.appendChild(expEl);
          whyContent.appendChild(item);
        }
      });

      if (hasExplanations) {
        whySection.style.display = "block";
      }
    } else {
      keywordsEl.innerHTML = '<span class="no-result">\u672a\u53d1\u73b0\u95ee\u9898\u5173\u952e\u8bcd</span>';
    }

    // Setup share button with context
    setupShareButton(pageTitle, result);
  }

  /**
   * Show daily stats summary when no active page result.
   * @param {HTMLElement} el
   */
  function showDailyStats(el) {
    var today = new Date().toISOString().slice(0, 10);
    var statsKey = "stats_" + today;
    chrome.storage.local.get([statsKey, "streak"], function (data) {
      var stats = data[statsKey];
      var streak = data["streak"] || 0;
      if (!stats || stats.total === 0) {
        el.classList.add("hidden");
        return;
      }
      var lines = [];
      lines.push("\u4eca\u65e5\u5df2\u68c0\u6d4b " + stats.total + " \u7bc7\u5185\u5bb9\uff1a" +
        stats.quality + " \u6b63\u5e38\u3001" + stats.suspicious + " \u5b58\u7591\u3001" + stats.junk + " \u9ad8\u98ce\u9669");
      if (streak > 1) {
        lines.push("\u8fde\u7eed " + streak + " \u5929\u4f7f\u7528\u9274\u771f\u4fdd\u62a4\u4f60\u7684\u9605\u8bfb\u8d28\u91cf \ud83c\udfaf");
      }
      el.textContent = lines.join("\n");
      el.classList.remove("hidden");
    });
  }

  /**
   * Setup share button click handler.
   * @param {string|null} pageTitle
   * @param {object} result
   */
  function setupShareButton(pageTitle, result) {
    var shareBtn = document.getElementById("share-btn");
    // Remove old listeners by replacing element
    var newBtn = shareBtn.cloneNode(true);
    shareBtn.parentNode.replaceChild(newBtn, shareBtn);

    newBtn.addEventListener("click", function () {
      var verdictEmoji = VERDICT_ICONS[result.verdict] || "\u2753";
      var title = pageTitle || "\u672a\u77e5\u9875\u9762";
      var text = "\ud83d\udd0d \u9274\u771f\u68c0\u6d4b\uff1a" + title + " " + verdictEmoji + " " + (result.explanation || "");
      navigator.clipboard.writeText(text).then(function () {
        var toast = document.getElementById("share-toast");
        toast.classList.remove("hidden");
        setTimeout(function () {
          toast.classList.add("hidden");
        }, 2000);
      });
    });
  }

  /**
   * Load and render the history list.
   */
  function loadHistory() {
    chrome.storage.local.get("history", function (data) {
      var history = data["history"] || [];
      var listEl = document.getElementById("history-list");
      listEl.innerHTML = "";
      if (history.length === 0) {
        listEl.innerHTML = '<span class="no-result">\u6682\u65e0\u8bb0\u5f55</span>';
        return;
      }
      // Show most recent first
      history.slice().reverse().forEach(function (entry) {
        var item = document.createElement("div");
        item.className = "history-item";
        var dot = document.createElement("span");
        dot.className = "history-dot " + (entry.verdict || "quality");
        var titleEl = document.createElement("span");
        titleEl.className = "history-title";
        var displayTitle = entry.title || "\u672a\u77e5\u9875\u9762";
        if (displayTitle.length > 30) {
          displayTitle = displayTitle.substring(0, 30) + "...";
        }
        titleEl.textContent = displayTitle;
        item.appendChild(dot);
        item.appendChild(titleEl);
        listEl.appendChild(item);
      });
    });
  }

  /**
   * Load the result for the current active tab with smooth loading transition.
   */
  function loadResult() {
    var container = document.querySelector(".container");
    var iconEl = document.getElementById("verdict-icon");
    var explanationEl = document.getElementById("explanation");
    var overlay = document.getElementById("updating-overlay");

    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs || tabs.length === 0) {
        displayResult(null, null);
        return;
      }

      const tab = tabs[0];
      const tabId = tab.id;
      const pageTitle = tab.title || null;
      const key = "result_" + tabId;

      chrome.storage.local.get(key, function (data) {
        const result = data[key] || null;

        if (result) {
          // We have a result, display it directly
          displayResult(result, pageTitle);
        } else {
          // No result yet - show brand icon with loading text
          if (container) container.classList.add("loading");
          iconEl.textContent = "\ud83d\udd0d";
          explanationEl.textContent = "\u68c0\u6d4b\u4e2d...";
        }
      });
    });
  }

  /**
   * Setup keyboard shortcuts for popup.
   * Esc: close popup, D: toggle details, S: share, F: feedback
   */
  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", function (e) {
      // Ignore if typing in an input
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

      var key = e.key.toUpperCase();

      if (e.key === "Escape") {
        window.close();
      } else if (key === "D") {
        var toggle = document.getElementById("details-toggle");
        if (toggle) toggle.click();
      } else if (key === "S") {
        var shareBtn = document.getElementById("share-btn");
        if (shareBtn) shareBtn.click();
      } else if (key === "F") {
        var feedbackBtn = document.getElementById("feedback-btn");
        if (feedbackBtn) feedbackBtn.click();
      }
    });
  }

  // Toggle details section
  document.getElementById("details-toggle").addEventListener("click", function () {
    const section = document.getElementById("details-section");
    const arrow = document.getElementById("toggle-arrow");
    section.classList.toggle("hidden");
    arrow.classList.toggle("expanded");
  });

  // Toggle why section
  document.getElementById("why-toggle").addEventListener("click", function () {
    const content = document.getElementById("why-content");
    const arrow = document.getElementById("why-arrow");
    content.classList.toggle("hidden");
    arrow.classList.toggle("expanded");
  });

  /**
   * Setup feedback button click handler.
   * Stores user disagreement in chrome.storage.local.
   */
  function setupFeedbackButton() {
    var feedbackBtn = document.getElementById("feedback-btn");
    feedbackBtn.addEventListener("click", function () {
      // Prevent double-submit
      if (feedbackBtn.disabled) return;
      feedbackBtn.disabled = true;
      feedbackBtn.style.opacity = "0.5";

      chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        var tab = tabs && tabs[0];
        var tabId = tab ? tab.id : null;
        var url = tab ? tab.url : "";
        var key = tabId ? "result_" + tabId : null;

        chrome.storage.local.get([key, "feedback"], function (data) {
          var result = key ? data[key] : null;
          var feedback = data["feedback"] || [];
          feedback.push({
            url: url,
            verdict: result ? result.verdict : "unknown",
            timestamp: Date.now(),
            user_disagrees: true
          });
          chrome.storage.local.set({ feedback: feedback }, function () {
            var toast = document.getElementById("feedback-toast");
            toast.classList.remove("hidden");
            setTimeout(function () {
              toast.classList.add("hidden");
            }, 2000);
          });
        });
      });
    });
  }

  /**
   * Setup highlight toggle button.
   * Sends message to content script to toggle keyword highlighting.
   */
  function setupHighlightButton() {
    var highlightBtn = document.getElementById("highlight-btn");
    chrome.storage.local.get("highlight_enabled", function (data) {
      var enabled = data["highlight_enabled"] || false;
      if (enabled) {
        highlightBtn.classList.add("active");
      }
    });

    highlightBtn.addEventListener("click", function () {
      chrome.storage.local.get("highlight_enabled", function (data) {
        var currentState = data["highlight_enabled"] || false;
        var newState = !currentState;
        chrome.storage.local.set({ highlight_enabled: newState });

        if (newState) {
          highlightBtn.classList.add("active");
        } else {
          highlightBtn.classList.remove("active");
        }

        // Send message to active tab's content script
        chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
          if (tabs && tabs[0]) {
            chrome.tabs.sendMessage(tabs[0].id, {
              type: "TOGGLE_HIGHLIGHT",
              enabled: newState
            });
          }
        });
      });
    });
  }

  /**
   * Display extension version from manifest.
   */
  function displayVersion() {
    var versionEl = document.getElementById("version-text");
    if (versionEl && chrome.runtime.getManifest) {
      var manifest = chrome.runtime.getManifest();
      versionEl.textContent = "v" + manifest.version;
    }
  }

  // Initialize popup
  checkOffline();
  setupHamburgerMenu();
  setupDismissButton();
  setupKeyboardShortcuts();
  loadResult();
  loadHistory();
  setupFeedbackButton();
  setupHighlightButton();
  displayVersion();
})();
