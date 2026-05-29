/**
 * content.js - Content script for extracting article text and showing results.
 *
 * Runs on: mp.weixin.qq.com, xiaohongshu.com, zhihu.com
 * Extracts article body text, sends to background for scoring,
 * and displays a floating traffic-light indicator.
 */

(function () {
  "use strict";

  /**
   * Extract article body text based on the current site's DOM structure.
   * @returns {string} The extracted text content.
   */
  function extractArticleText() {
    const host = window.location.hostname;
    let contentEl = null;

    if (host.includes("mp.weixin.qq.com")) {
      // WeChat articles
      contentEl =
        document.getElementById("js_content") ||
        document.querySelector(".rich_media_content");
    } else if (host.includes("xiaohongshu.com")) {
      // Xiaohongshu notes
      contentEl =
        document.querySelector(".note-content") ||
        document.getElementById("detail-desc") ||
        document.querySelector('[class*="note"]');
    } else if (host.includes("zhihu.com")) {
      // Zhihu answers/articles
      contentEl =
        document.querySelector(".RichContent-inner") ||
        document.querySelector(".Post-RichText") ||
        document.querySelector(".RichText");
    }

    if (contentEl) {
      return contentEl.innerText || contentEl.textContent || "";
    }

    // Fallback: try common article selectors
    const fallback =
      document.querySelector("article") ||
      document.querySelector('[role="main"]') ||
      document.querySelector(".content");
    return fallback ? fallback.innerText || fallback.textContent || "" : "";
  }

  /**
   * Create and inject a floating traffic-light indicator in the bottom-right corner.
   * @param {{score: number, verdict: string, explanation: string}} result
   */
  function showIndicator(result) {
    // Remove any existing indicator
    const existing = document.getElementById("junk-detector-indicator");
    if (existing) existing.remove();

    const colors = {
      quality: "#34C759",
      suspicious: "#FF9500",
      junk: "#FF3B30"
    };

    const icons = {
      quality: "\u2705",
      suspicious: "\u26a0\ufe0f",
      junk: "\ud83d\udea8"
    };

    const indicator = document.createElement("div");
    indicator.id = "junk-detector-indicator";
    indicator.title = result.explanation;
    indicator.innerHTML = `
      <span style="font-size: 16px;">${icons[result.verdict] || "\u2753"}</span>
      <span style="font-size: 12px; margin-left: 4px; font-weight: 500;">${result.score}</span>
    `;

    Object.assign(indicator.style, {
      position: "fixed",
      bottom: "20px",
      right: "20px",
      zIndex: "2147483647",
      display: "flex",
      alignItems: "center",
      padding: "8px 12px",
      borderRadius: "20px",
      backgroundColor: "white",
      border: `2px solid ${colors[result.verdict] || "#ccc"}`,
      boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
      cursor: "pointer",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      transition: "transform 0.2s ease, box-shadow 0.2s ease"
    });

    indicator.addEventListener("mouseenter", () => {
      indicator.style.transform = "scale(1.05)";
      indicator.style.boxShadow = "0 4px 16px rgba(0,0,0,0.2)";
    });
    indicator.addEventListener("mouseleave", () => {
      indicator.style.transform = "scale(1)";
      indicator.style.boxShadow = "0 2px 12px rgba(0,0,0,0.15)";
    });

    document.body.appendChild(indicator);
  }

  /**
   * Main execution: extract text, score it, and display result.
   */
  function run() {
    const text = extractArticleText();
    if (!text || text.trim().length < 20) {
      return; // Not enough content to analyze
    }

    // Send to background script for scoring
    chrome.runtime.sendMessage(
      { type: "SCORE_CONTENT", text: text },
      function (response) {
        if (response && response.result) {
          showIndicator(response.result);
        }
      }
    );
  }

  // Run after page load with a small delay to ensure DOM is ready
  if (document.readyState === "complete") {
    setTimeout(run, 1000);
  } else {
    window.addEventListener("load", () => setTimeout(run, 1000));
  }
})();
