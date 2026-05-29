/**
 * options.js - Settings page logic for the Chrome extension.
 *
 * Saves and loads settings from chrome.storage.sync:
 * - sensitivity: 'strict' | 'standard' | 'relaxed'
 * - excludedSites: array of domain strings
 * - notifications: boolean
 */

(function () {
  "use strict";

  var DEFAULTS = {
    sensitivity: "standard",
    excludedSites: [],
    notifications: true
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

    chrome.storage.sync.set({
      sensitivity: sensitivity,
      excludedSites: excludedSites,
      notifications: notifications
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

  // Auto-save on any change
  document.querySelectorAll('input[name="sensitivity"]').forEach(function (radio) {
    radio.addEventListener("change", saveSettings);
  });
  document.getElementById("excluded-sites").addEventListener("input", saveSettings);
  document.getElementById("notifications-toggle").addEventListener("change", saveSettings);

  // Load settings on page open
  loadSettings();
})();
