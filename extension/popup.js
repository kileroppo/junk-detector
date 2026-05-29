/**
 * popup.js - Popup UI logic for the Chrome extension.
 *
 * Reads the latest scoring result from chrome.storage.local and displays it.
 */

(function () {
  "use strict";

  const VERDICT_ICONS = {
    quality: "\u2705",
    suspicious: "\u26a0\ufe0f",
    junk: "\ud83d\udea8"
  };

  /**
   * Update the popup UI with scoring results.
   * @param {object|null} result
   */
  function displayResult(result) {
    const iconEl = document.getElementById("verdict-icon");
    const explanationEl = document.getElementById("explanation");
    const scoreEl = document.getElementById("score-value");
    const keywordsEl = document.getElementById("keywords-list");

    if (!result) {
      iconEl.textContent = "\u2753";
      explanationEl.textContent = "\u8bf7\u5728\u652f\u6301\u7684\u7f51\u7ad9\u4e0a\u6253\u5f00\u6587\u7ae0\u540e\u518d\u68c0\u6d4b";
      scoreEl.textContent = "--";
      scoreEl.className = "score-value";
      return;
    }

    iconEl.textContent = VERDICT_ICONS[result.verdict] || "\u2753";
    explanationEl.textContent = result.explanation || "";

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
  }

  /**
   * Load the result for the current active tab.
   */
  function loadResult() {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs || tabs.length === 0) {
        displayResult(null);
        return;
      }

      const tabId = tabs[0].id;
      const key = "result_" + tabId;
      chrome.storage.local.get(key, function (data) {
        const result = data[key] || null;
        displayResult(result);
      });
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

  // Load result on popup open
  loadResult();
})();
