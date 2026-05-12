/**
 * i18n.js — Lightweight internationalization engine for Seedance Wizard
 *
 * No dependencies. Zero build tools. Vanilla JS only.
 *
 * Features:
 *   - Auto-detect language from navigator.language or localStorage
 *   - Load locale JSON via fetch
 *   - Replace textContent of all [data-i18n] elements
 *   - Replace placeholder of all [data-i18n-placeholder] elements
 *   - Replace title of all [data-i18n-title] elements
 *   - Expose window.__t(key, ...args) for programmatic use in JS
 *   - Expose window.__setLocale(lang) to switch language at runtime
 *   - Expose window.__getLocale() to get current locale
 *
 * Usage in HTML:
 *   <span data-i18n="keyName">Fallback text</span>
 *   <input data-i18n-placeholder="keyName" placeholder="Fallback">
 *   <button data-i18n-title="keyName" title="Fallback">
 *
 * Usage in JS:
 *   window.__t('keyName')
 *   window.__t('keyName', 'arg0', 'arg1')  // replaces {0}, {1}
 *   window.__setLocale('zh')
 *   window.__getLocale()
 *
 * License: MIT
 * Copyright (c) 2025 Seedance Wizard Contributors
 */
(function () {
  "use strict";

  var SUPPORTED_LOCALES = ["zh", "en"];
  var DEFAULT_LOCALE = "en";
  var STORAGE_KEY = "seedance_locale";

  var _translations = {};  // key → translated string
  var _currentLocale = DEFAULT_LOCALE;

  /**
   * Determine the initial locale:
   *   1. Check localStorage for a user preference
   *   2. Fall back to navigator.language (zh* → zh, otherwise → en)
   */
  function detectLocale() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED_LOCALES.indexOf(stored) !== -1) {
        return stored;
      }
    } catch (e) {
      // localStorage may be unavailable
    }

    try {
      var lang = (navigator.language || navigator.userLanguage || "").toLowerCase();
      if (lang.indexOf("zh") === 0) {
        return "zh";
      }
    } catch (e) {
      // navigator.language may be unavailable
    }

    return DEFAULT_LOCALE;
  }

  /**
   * Replace placeholders {0}, {1}, ... in a template string.
   */
  function format(str, args) {
    if (!args || args.length === 0) return str;
    return str.replace(/\{(\d+)\}/g, function (match, index) {
      return index < args.length ? args[index] : match;
    });
  }

  /**
   * Load the locale JSON file for the given language.
   * Returns a Promise that resolves to the translations object.
   */
  function loadLocale(locale) {
    var url = "i18n/" + locale + ".json";
    return fetch(url)
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("Failed to load locale: " + locale + " (HTTP " + resp.status + ")");
        }
        return resp.json();
      })
      .catch(function (err) {
        console.warn("[i18n] Cannot load locale " + locale + ": " + err.message);
        // Fall back to English if the requested locale fails
        if (locale !== DEFAULT_LOCALE) {
          return loadLocale(DEFAULT_LOCALE);
        }
        // If even English fails, return an empty object (keep HTML fallbacks)
        return {};
      });
  }

  /**
   * Apply translations to the DOM.
   * Walks [data-i18n], [data-i18n-placeholder], [data-i18n-title] elements
   * and replaces their text/placeholder/title with translated strings.
   */
  function applyTranslations() {
    // Text content
    var textEls = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < textEls.length; i++) {
      var el = textEls[i];
      var key = el.getAttribute("data-i18n");
      if (key && _translations[key] !== undefined) {
        el.textContent = _translations[key];
      }
    }

    // Placeholder attributes
    var placeholderEls = document.querySelectorAll("[data-i18n-placeholder]");
    for (var j = 0; j < placeholderEls.length; j++) {
      var pel = placeholderEls[j];
      var pkey = pel.getAttribute("data-i18n-placeholder");
      if (pkey && _translations[pkey] !== undefined) {
        pel.setAttribute("placeholder", _translations[pkey]);
      }
    }

    // Title attributes
    var titleEls = document.querySelectorAll("[data-i18n-title]");
    for (var k = 0; k < titleEls.length; k++) {
      var tel = titleEls[k];
      var tkey = tel.getAttribute("data-i18n-title");
      if (tkey && _translations[tkey] !== undefined) {
        tel.setAttribute("title", _translations[tkey]);
      }
    }

    // Update <html lang> attribute
    document.documentElement.setAttribute("lang", _currentLocale === "zh" ? "zh-CN" : "en");
  }

  /**
   * Translate a key. Accepts optional arguments for {0}, {1}, ... replacement.
   * Returns the key itself if no translation is found.
   */
  function __t(key) {
    if (!key) return "";

    var template = _translations[key];
    if (template === undefined) {
      // Missing translation: return the key as a visible hint
      console.debug("[i18n] Missing translation for key:", key);
      return key;
    }

    // Collect replacement arguments (everything after the first argument)
    var args = [];
    for (var i = 1; i < arguments.length; i++) {
      args.push(arguments[i]);
    }

    return format(template, args);
  }

  /**
   * Switch to a different locale. Reloads translations and re-renders the DOM.
   * Persists the choice to localStorage.
   */
  function __setLocale(locale) {
    if (SUPPORTED_LOCALES.indexOf(locale) === -1) {
      console.warn("[i18n] Unsupported locale:", locale, "- falling back to", DEFAULT_LOCALE);
      locale = DEFAULT_LOCALE;
    }

    _currentLocale = locale;

    try {
      localStorage.setItem(STORAGE_KEY, locale);
    } catch (e) {
      // localStorage may be unavailable
    }

    return loadLocale(locale).then(function (translations) {
      _translations = translations;
      applyTranslations();

      // Dispatch a custom event so other scripts can react
      try {
        document.dispatchEvent(
          new CustomEvent("seedance_locale_changed", { detail: { locale: locale } })
        );
      } catch (e) {
        // CustomEvent not supported — fire a simple event
        var evt = document.createEvent("Event");
        evt.initEvent("seedance_locale_changed", true, true);
        evt.detail = { locale: locale };
        document.dispatchEvent(evt);
      }

      return translations;
    });
  }

  /**
   * Returns the current locale string (e.g., "zh" or "en").
   */
  function __getLocale() {
    return _currentLocale;
  }

  // ── Bootstrap ──

  var initialLocale = detectLocale();

  // Expose public API as early as possible (before translations load)
  // so inline scripts can call window.__t() immediately.
  // Calls made before loading completes will return the key itself
  // (fallback), which is acceptable for a single-frame paint.
  window.__t = __t;
  window.__setLocale = __setLocale;
  window.__getLocale = __getLocale;

  // Load the detected locale and apply to DOM
  __setLocale(initialLocale).catch(function (err) {
    console.error("[i18n] Initialization failed:", err);
    // DOM keeps its original (English) fallback text
  });
})();
