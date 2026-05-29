/**
 * content.js - Content script for extracting article text and showing results.
 *
 * Runs on: mp.weixin.qq.com, xiaohongshu.com, zhihu.com, juejin.cn, weibo.com
 * Extracts article body text, sends to background for scoring,
 * and displays a floating traffic-light indicator.
 * Features: toast notification, scroll-aware timing, paywall detection, dismiss check.
 */

(function () {
  "use strict";

  // Scroll-aware timing: track last scroll timestamp
  var lastScrollTime = Date.now();
  window.addEventListener("scroll", function () {
    lastScrollTime = Date.now();
  }, { passive: true });

  /**
   * Detect if the page is being viewed on a mobile device.
   * @returns {boolean}
   */
  function isMobile() {
    return document.documentElement.clientWidth < 768 ||
      document.querySelector('meta[name="viewport"][content*="width=device-width"]') !== null;
  }

  /**
   * Detect paywalled content.
   * Checks for known paywall indicators on supported platforms.
   * @returns {boolean}
   */
  function detectPaywall() {
    // Zhihu salt select (paid content)
    if (document.querySelector(".zu-pay-tip")) return true;
    // WeChat pay-to-read
    if (document.querySelector(".pay-content-mask")) return true;
    // Generic paywall class
    if (document.querySelector(".article-paywall")) return true;
    return false;
  }

  /**
   * Check if the current URL has been dismissed within the last 24 hours.
   * @param {function} callback - Called with true if dismissed (should skip), false otherwise
   */
  function checkDismissed(callback) {
    var currentUrl = window.location.href;
    chrome.storage.local.get("dismissals", function (data) {
      var dismissals = data.dismissals || [];
      var now = Date.now();
      var twentyFourHours = 24 * 60 * 60 * 1000;
      var isDismissed = dismissals.some(function (d) {
        return d.url === currentUrl && (now - d.timestamp) < twentyFourHours;
      });
      callback(isDismissed);
    });
  }

  /**
   * Show a toast notification for suspicious/junk verdicts.
   * Fixed position at top-right, auto-fades after 5 seconds.
   * Respects scroll-aware timing (waits for user to stop scrolling).
   * @param {{verdict: string, explanation: string}} result
   */
  function showToastNotification(result) {
    if (result.verdict !== "suspicious" && result.verdict !== "junk") return;

    // Check notifications setting
    chrome.storage.sync.get("notifications", function (data) {
      if (data.notifications === false) return;

      // Wait until user has paused scrolling for 2+ seconds
      function waitForScrollPause() {
        var elapsed = Date.now() - lastScrollTime;
        if (elapsed >= 2000) {
          renderToast(result);
        } else {
          setTimeout(waitForScrollPause, 2000 - elapsed);
        }
      }
      waitForScrollPause();
    });
  }

  /**
   * Render the toast notification element.
   * @param {{verdict: string, explanation: string}} result
   */
  function renderToast(result) {
    // Remove any existing toast
    var existing = document.getElementById("junk-detector-toast");
    if (existing) existing.remove();

    var borderColor = result.verdict === "junk" ? "#FF3B30" : "#FF9500";
    var toast = document.createElement("div");
    toast.id = "junk-detector-toast";

    var shortExplanation = (result.explanation || "").substring(0, 60);
    toast.innerHTML = '<span style="margin-right:6px;">\u26a0\ufe0f</span>' +
      '<span>\u8fd9\u7bc7\u5185\u5bb9\u53ef\u80fd\u6709\u95ee\u9898</span>' +
      (shortExplanation ? '<div style="font-size:11px;color:#6b7280;margin-top:4px;">' + shortExplanation + '</div>' : '');

    Object.assign(toast.style, {
      position: "fixed",
      top: "16px",
      right: "16px",
      zIndex: "2147483647",
      width: "300px",
      padding: "12px 16px",
      borderRadius: "8px",
      backgroundColor: "#ffffff",
      borderLeft: "4px solid " + borderColor,
      boxShadow: "0 4px 16px rgba(0,0,0,0.15)",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      fontSize: "13px",
      color: "#1d1d1f",
      opacity: "0",
      transform: "translateX(20px)",
      transition: "opacity 0.4s ease, transform 0.4s ease"
    });

    document.body.appendChild(toast);

    // Trigger slide-in
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        toast.style.opacity = "1";
        toast.style.transform = "translateX(0)";
      });
    });

    // Auto-fade after 5 seconds
    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 400);
    }, 5000);
  }

  /**
   * Extract article body text based on the current site's DOM structure.
   * @returns {string} The extracted text content.
   */
  function extractArticleText() {
    const host = window.location.hostname;
    let contentEl = null;

    if (host.includes("mp.weixin.qq.com")) {
      // WeChat articles - desktop and mobile
      contentEl =
        document.getElementById("js_content") ||
        document.querySelector(".rich_media_content");
      // Mobile-specific fallbacks
      if (!contentEl && isMobile()) {
        contentEl =
          document.querySelector(".weui-article__section") ||
          document.querySelector(".rich_media_area_primary");
      }
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
    } else if (host.includes("juejin.cn")) {
      // Juejin articles
      contentEl =
        document.querySelector(".article-content") ||
        document.querySelector(".markdown-body");
    } else if (host.includes("weibo.com")) {
      // Weibo posts
      contentEl =
        document.querySelector(".detail_wbtext_4CRf9") ||
        document.querySelector(".wbpro-feed-content") ||
        document.querySelector('[class*="Feed_body"]');
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
   * Fades in smoothly and shows a tooltip on hover with one-line verdict.
   * Uses severity tier for colors and labels when available.
   * @param {{score: number, verdict: string, explanation: string, severity: string}} result
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

    // Severity-based display (preferred when severity is available)
    var severityInfo = null;
    if (result.severity && typeof SEVERITY_MAP !== "undefined") {
      severityInfo = SEVERITY_MAP[result.severity] || null;
    }

    var displayEmoji;
    var displayLabel;
    var displayColor;

    if (severityInfo) {
      displayEmoji = severityInfo.emoji;
      displayLabel = severityInfo.label;
      displayColor = severityInfo.color;
    } else {
      var icons = {
        quality: "\u2705",
        suspicious: "\u26a0\ufe0f",
        junk: "\ud83d\udea8"
      };
      displayEmoji = icons[result.verdict] || "\u2753";
      displayLabel = String(result.score);
      displayColor = colors[result.verdict] || "#ccc";
    }

    const indicator = document.createElement("div");
    indicator.id = "junk-detector-indicator";
    indicator.title = result.explanation || "";
    indicator.innerHTML = '<span style="font-size: 16px;">' + displayEmoji + '</span>' +
      '<span style="font-size: 12px; margin-left: 4px; font-weight: 500;">' + displayLabel + '</span>';

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
      border: "2px solid " + displayColor,
      boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
      cursor: "pointer",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      opacity: "0",
      transform: "translateY(8px)",
      transition: "opacity 0.4s ease, transform 0.4s ease, box-shadow 0.2s ease"
    });

    document.body.appendChild(indicator);

    // Trigger fade-in after append
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        indicator.style.opacity = "1";
        indicator.style.transform = "translateY(0)";
      });
    });

    indicator.addEventListener("mouseenter", function () {
      indicator.style.transform = "scale(1.05)";
      indicator.style.boxShadow = "0 4px 16px rgba(0,0,0,0.2)";
    });
    indicator.addEventListener("mouseleave", function () {
      indicator.style.transform = "scale(1) translateY(0)";
      indicator.style.boxShadow = "0 2px 12px rgba(0,0,0,0.15)";
    });
  }

  /**
   * Show paywall indicator instead of scoring.
   */
  function showPaywallIndicator() {
    var existing = document.getElementById("junk-detector-indicator");
    if (existing) existing.remove();

    var indicator = document.createElement("div");
    indicator.id = "junk-detector-indicator";
    indicator.innerHTML = '<span style="font-size: 14px;">\ud83d\udd12 \u65e0\u6cd5\u68c0\u6d4b\u4ed8\u8d39\u5185\u5bb9</span>';

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
      border: "2px solid #9ca3af",
      boxShadow: "0 2px 12px rgba(0,0,0,0.15)",
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      opacity: "0",
      transform: "translateY(8px)",
      transition: "opacity 0.4s ease, transform 0.4s ease"
    });

    document.body.appendChild(indicator);

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        indicator.style.opacity = "1";
        indicator.style.transform = "translateY(0)";
      });
    });
  }

  /**
   * Check if the current domain is whitelisted (trusted).
   * @param {function} callback - Called with true if should proceed, false if whitelisted.
   */
  function checkWhitelist(callback) {
    chrome.storage.sync.get("whitelist", function (data) {
      var whitelist = data.whitelist || [];
      var domain = window.location.hostname;
      callback(!whitelist.includes(domain));
    });
  }

  /**
   * Main execution: extract text, score it, and display result.
   */
  function run() {
    // Check if URL is dismissed within last 24 hours
    checkDismissed(function (isDismissed) {
      if (isDismissed) return;

      // Check whitelist before scoring
      checkWhitelist(function (shouldProceed) {
        if (!shouldProceed) return;

        // Check for paywalled content
        if (detectPaywall()) {
          showPaywallIndicator();
          return;
        }

        var text = extractArticleText();
        if (!text || text.trim().length < 20) {
          return; // Not enough content to analyze
        }

        // Send to background script for scoring
        try {
          chrome.runtime.sendMessage(
            { type: "SCORE_CONTENT", text: text },
            function (response) {
              if (chrome.runtime.lastError) return;
              if (response && response.result) {
                showIndicator(response.result);
                showToastNotification(response.result);
              }
            }
          );
        } catch (e) {
          // Gracefully handle disconnected extension context
        }
      });
    });
  }

  // Track current URL for SPA navigation detection
  let lastUrl = window.location.href;

  /**
   * Watch for SPA navigation via URL polling.
   * Most supported platforms (Zhihu, Xiaohongshu, Weibo, Juejin)
   * use client-side routing without full page reloads.
   */
  function watchForNavigation() {
    setInterval(function () {
      if (window.location.href !== lastUrl) {
        lastUrl = window.location.href;
        // Delay re-scoring to allow new content to render
        setTimeout(run, 800);
      }
    }, 1000);
  }

  /**
   * Compute a simple hash of text content for change detection.
   * Uses text length combined with first/last 20 characters.
   * @param {string} text
   * @returns {string}
   */
  function simpleHash(text) {
    if (!text) return "";
    var len = text.length;
    var first = text.substring(0, 20);
    var last = text.substring(Math.max(0, len - 20));
    return len + ":" + first + ":" + last;
  }

  /**
   * Observe DOM mutations for content container changes.
   * This catches in-page content swaps that don't change the URL
   * (e.g., Zhihu answer expansion, Xiaohongshu modal overlays).
   * Uses a content hash with debounce to avoid excessive scoring.
   */
  function observeContentChanges() {
    var lastContentHash = "";
    var observer = new MutationObserver(function () {
      clearTimeout(observer._debounce);
      observer._debounce = setTimeout(function () {
        var text = extractArticleText();
        var hash = simpleHash(text);
        if (hash !== lastContentHash && text.length > 50) {
          lastContentHash = hash;
          scoreAndDisplay(text);
        }
      }, 500);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  /**
   * Score text content and display the indicator.
   * @param {string} text
   */
  function scoreAndDisplay(text) {
    if (!text || text.trim().length < 20) return;
    try {
      chrome.runtime.sendMessage(
        { type: "SCORE_CONTENT", text: text },
        function (response) {
          if (chrome.runtime.lastError) return;
          if (response && response.result) {
            showIndicator(response.result);
          }
        }
      );
    } catch (e) {
      // Gracefully handle disconnected extension context
    }
  }

  /**
   * Score individual feed items on supported platforms (Zhihu, Weibo).
   * Uses data attributes to avoid re-scoring already processed items.
   */
  function scoreFeedItems() {
    // Zhihu feed items
    var zhihuItems = document.querySelectorAll('.ContentItem:not([data-jz-scored])');
    // Weibo feed items
    var weiboItems = document.querySelectorAll('[class*="Feed_body"]:not([data-jz-scored])');
    // Juejin feed items
    var juejinItems = document.querySelectorAll('.entry-list .item:not([data-jz-scored])');

    var allItems = [].concat(
      Array.prototype.slice.call(zhihuItems),
      Array.prototype.slice.call(weiboItems),
      Array.prototype.slice.call(juejinItems)
    );

    allItems.forEach(function (item) {
      item.setAttribute('data-jz-scored', 'true');
      var text = item.innerText || item.textContent || "";
      if (text.length > 50) {
        try {
          chrome.runtime.sendMessage(
            { type: "SCORE_CONTENT", text: text },
            function (resp) {
              if (chrome.runtime.lastError) return;
              if (resp && resp.result) {
                addMiniBadge(item, resp.result);
              }
            }
          );
        } catch (e) {
          // Gracefully handle disconnected extension context
        }
      }
    });
  }

  /**
   * Add a small colored badge to a feed item indicating its quality score.
   * @param {HTMLElement} element - The feed item element
   * @param {{verdict: string, score: number}} result - Scoring result
   */
  function addMiniBadge(element, result) {
    var existing = element.querySelector('.jz-mini-badge');
    if (existing) return;

    var colors = {
      quality: "#34C759",
      suspicious: "#FF9500",
      junk: "#FF3B30"
    };

    var badge = document.createElement('span');
    badge.className = 'jz-mini-badge';
    badge.title = result.explanation || result.verdict;
    badge.style.cssText = [
      'display: inline-block',
      'width: 8px',
      'height: 8px',
      'border-radius: 50%',
      'position: absolute',
      'top: 8px',
      'right: 8px',
      'z-index: 100',
      'background-color: ' + (colors[result.verdict] || '#ccc'),
      'box-shadow: 0 1px 3px rgba(0,0,0,0.2)',
      'pointer-events: none'
    ].join(';');

    element.style.position = 'relative';
    element.appendChild(badge);
  }

  /**
   * Observe DOM mutations for feed content and score new items.
   * Uses requestIdleCallback to defer scoring of new feed items.
   */
  function observeFeedChanges() {
    var feedObserver = new MutationObserver(function () {
      if (typeof requestIdleCallback !== 'undefined') {
        requestIdleCallback(function () { scoreFeedItems(); });
      } else {
        setTimeout(function () { scoreFeedItems(); }, 200);
      }
    });
    feedObserver.observe(document.body, { childList: true, subtree: true });
  }

  // Run after page load using requestIdleCallback for better performance.
  // This ensures the content script doesn't compete with initial page rendering.
  if (document.readyState === "complete") {
    if (window.requestIdleCallback) {
      requestIdleCallback(function() { run(); watchForNavigation(); observeContentChanges(); scoreFeedItems(); observeFeedChanges(); }, {timeout: 2000});
    } else {
      setTimeout(function() { run(); watchForNavigation(); observeContentChanges(); scoreFeedItems(); observeFeedChanges(); }, 1000);
    }
  } else {
    window.addEventListener("load", function () {
      if (window.requestIdleCallback) {
        requestIdleCallback(function() { run(); watchForNavigation(); observeContentChanges(); scoreFeedItems(); observeFeedChanges(); }, {timeout: 2000});
      } else {
        setTimeout(function() { run(); watchForNavigation(); observeContentChanges(); scoreFeedItems(); observeFeedChanges(); }, 1000);
      }
    });
  }

  // -----------------------------------------------------------------------
  // In-page keyword highlighting
  // -----------------------------------------------------------------------

  /**
   * Highlight matched keywords on the page with colored underlines.
   * @param {{matchedKeywords: string[], verdict: string}} result
   */
  function highlightKeywords(result) {
    if (!result || !result.matchedKeywords || result.matchedKeywords.length === 0) return;

    // Remove previous highlights first
    removeHighlights();

    // Inject highlight styles
    var existingStyle = document.getElementById('jz-highlight-styles');
    if (!existingStyle) {
      var style = document.createElement('style');
      style.id = 'jz-highlight-styles';
      style.textContent = [
        '.jz-highlight-scam { background-color: rgba(239, 68, 68, 0.15); border-bottom: 2px solid #EF4444; }',
        '.jz-highlight-anxiety { background-color: rgba(245, 158, 11, 0.15); border-bottom: 2px solid #F59E0B; }',
        '.jz-highlight-advertorial { background-color: rgba(59, 130, 246, 0.15); border-bottom: 2px solid #3B82F6; }'
      ].join('\n');
      document.head.appendChild(style);
    }

    // Determine highlight class based on verdict
    var highlightClass = 'jz-highlight-scam';
    if (result.verdict === 'suspicious') {
      highlightClass = 'jz-highlight-anxiety';
    }

    // Walk text nodes and wrap matched keywords
    var keywords = result.matchedKeywords;
    var walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      null,
      false
    );

    var textNodes = [];
    while (walker.nextNode()) {
      textNodes.push(walker.currentNode);
    }

    textNodes.forEach(function (node) {
      // Skip nodes inside our own elements
      if (node.parentElement && (
        node.parentElement.id === 'junk-detector-indicator' ||
        node.parentElement.id === 'junk-detector-toast' ||
        node.parentElement.classList.contains('jz-highlight-scam') ||
        node.parentElement.classList.contains('jz-highlight-anxiety') ||
        node.parentElement.classList.contains('jz-highlight-advertorial')
      )) return;

      var text = node.textContent;
      var matched = false;
      keywords.forEach(function (kw) {
        if (text.indexOf(kw) !== -1) matched = true;
      });

      if (!matched) return;

      var fragment = document.createDocumentFragment();
      var remaining = text;

      while (remaining.length > 0) {
        var earliestIdx = -1;
        var earliestKw = '';

        keywords.forEach(function (kw) {
          var idx = remaining.indexOf(kw);
          if (idx !== -1 && (earliestIdx === -1 || idx < earliestIdx)) {
            earliestIdx = idx;
            earliestKw = kw;
          }
        });

        if (earliestIdx === -1) {
          fragment.appendChild(document.createTextNode(remaining));
          break;
        }

        if (earliestIdx > 0) {
          fragment.appendChild(document.createTextNode(remaining.substring(0, earliestIdx)));
        }

        var span = document.createElement('span');
        span.className = highlightClass + ' jz-highlight';
        span.textContent = earliestKw;
        fragment.appendChild(span);

        remaining = remaining.substring(earliestIdx + earliestKw.length);
      }

      node.parentNode.replaceChild(fragment, node);
    });
  }

  /**
   * Remove all highlight marks from the page, restoring original text.
   */
  function removeHighlights() {
    var highlights = document.querySelectorAll('.jz-highlight');
    highlights.forEach(function (el) {
      var parent = el.parentNode;
      parent.replaceChild(document.createTextNode(el.textContent), el);
      parent.normalize();
    });
  }

  // Listen for messages from popup to toggle highlights
  chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (message.type === 'TOGGLE_HIGHLIGHT') {
      if (message.enabled) {
        // Get current result and highlight
        chrome.storage.local.get(null, function (data) {
          // Find result for current tab
          var keys = Object.keys(data);
          var resultKey = keys.find(function (k) { return k.startsWith('result_'); });
          var result = resultKey ? data[resultKey] : null;
          if (result) {
            highlightKeywords(result);
          }
        });
      } else {
        removeHighlights();
      }
      sendResponse({ ok: true });
    }
    return true;
  });
})();
