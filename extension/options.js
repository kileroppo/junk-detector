/**
 * options.js - Settings page logic for the Chrome extension.
 *
 * Saves and loads settings from chrome.storage.sync:
 * - sensitivity: 'strict' | 'standard' | 'relaxed'
 * - excludedSites: array of domain strings
 * - notifications: boolean
 * - sound_enabled: boolean
 *
 * Also handles history export (CSV) and clear history.
 */

(function () {
  "use strict";

  var DEFAULTS = {
    sensitivity: "standard",
    excludedSites: [],
    notifications: true,
    sound_enabled: false
  };

  /**
   * Load saved settings and populate the UI.
   */
  function loadSettings() {
    chrome.storage.sync.get(DEFAULTS, function (settings) {
      // Sensitivity radio
      var radios = document.querySelectorAll('input[name="sensitivity"]');
      radios.forEach(function (radio) {
        radio.checked = radio.value === settings.sensitivity;
      });

      // Excluded sites
      var textarea = document.getElementById("excluded-sites");
      textarea.value = (settings.excludedSites || []).join("\n");

      // Notifications toggle
      var toggle = document.getElementById("notifications-toggle");
      toggle.checked = settings.notifications !== false;

      // Sound toggle
      var soundToggle = document.getElementById("sound-toggle");
      soundToggle.checked = settings.sound_enabled === true;
    });
  }

  /**
   * Save current UI state to chrome.storage.sync.
   */
  function saveSettings() {
    var sensitivity = "standard";
    var radios = document.querySelectorAll('input[name="sensitivity"]');
    radios.forEach(function (radio) {
      if (radio.checked) sensitivity = radio.value;
    });

    var textarea = document.getElementById("excluded-sites");
    var excludedSites = textarea.value
      .split("\n")
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });

    var notifications = document.getElementById("notifications-toggle").checked;
    var soundEnabled = document.getElementById("sound-toggle").checked;

    chrome.storage.sync.set({
      sensitivity: sensitivity,
      excludedSites: excludedSites,
      notifications: notifications,
      sound_enabled: soundEnabled
    }, function () {
      showSaveMessage();
    });
  }

  /**
   * Show brief save confirmation.
   */
  function showSaveMessage() {
    var msg = document.getElementById("save-msg");
    msg.classList.add("visible");
    setTimeout(function () {
      msg.classList.remove("visible");
    }, 2000);
  }

  /**
   * Export history as CSV file download.
   */
  function exportHistory() {
    chrome.storage.local.get("history", function (data) {
      var history = data.history || [];
      if (history.length === 0) {
        alert("\u6682\u65e0\u5386\u53f2\u8bb0\u5f55");
        return;
      }

      var csv = "\u65e5\u671f,URL,\u6807\u9898,\u7ed3\u679c\n";
      history.forEach(function (entry) {
        var date = entry.timestamp ? new Date(entry.timestamp).toLocaleString("zh-CN") : "";
        var url = (entry.url || "").replace(/,/g, " ");
        var title = (entry.title || "").replace(/,/g, " ");
        var verdict = entry.verdict || "";
        csv += date + "," + url + "," + title + "," + verdict + "\n";
      });

      var blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "jianzen-history.csv";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    });
  }

  /**
   * Clear all history with confirmation.
   */
  function clearHistory() {
    if (!confirm("\u786e\u5b9a\u8981\u6e05\u9664\u6240\u6709\u68c0\u6d4b\u5386\u53f2\u8bb0\u5f55\u5417\uff1f")) return;
    chrome.storage.local.remove("history", function () {
      showSaveMessage();
    });
  }

  // Auto-save on any change
  document.querySelectorAll('input[name="sensitivity"]').forEach(function (radio) {
    radio.addEventListener("change", saveSettings);
  });
  document.getElementById("excluded-sites").addEventListener("input", saveSettings);
  document.getElementById("notifications-toggle").addEventListener("change", saveSettings);
  document.getElementById("sound-toggle").addEventListener("change", saveSettings);

  // History management buttons
  document.getElementById("export-history-btn").addEventListener("click", exportHistory);
  document.getElementById("clear-history-btn").addEventListener("click", clearHistory);

  /**
   * Load and render the whitelist.
   */
  function loadWhitelist() {
    chrome.storage.sync.get("whitelist", function (data) {
      var whitelist = data.whitelist || [];
      var container = document.getElementById("whitelist-container");
      container.innerHTML = "";

      if (whitelist.length === 0) {
        container.innerHTML = '<span class="no-result">\u6682\u65e0\u4fe1\u4efb\u7f51\u7ad9</span>';
        return;
      }

      whitelist.forEach(function (domain) {
        var item = document.createElement("div");
        item.className = "whitelist-item";

        var domainEl = document.createElement("span");
        domainEl.className = "domain";
        domainEl.textContent = domain;

        var removeBtn = document.createElement("button");
        removeBtn.className = "whitelist-remove";
        removeBtn.textContent = "\u2715";
        removeBtn.title = "\u79fb\u9664";
        removeBtn.addEventListener("click", function () {
          removeFromWhitelist(domain);
        });

        item.appendChild(domainEl);
        item.appendChild(removeBtn);
        container.appendChild(item);
      });
    });
  }

  /**
   * Remove a domain from the whitelist.
   * @param {string} domain
   */
  function removeFromWhitelist(domain) {
    chrome.storage.sync.get("whitelist", function (data) {
      var whitelist = data.whitelist || [];
      whitelist = whitelist.filter(function (d) { return d !== domain; });
      chrome.storage.sync.set({ whitelist: whitelist }, function () {
        loadWhitelist();
        showSaveMessage();
      });
    });
  }

  // Load settings on page open
  loadSettings();
  loadWhitelist();
})();
