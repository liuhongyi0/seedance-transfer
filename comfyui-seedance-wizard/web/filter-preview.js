/**
 * filter-preview.js — CSS Filter Engine for Seedance Wizard
 *
 * Maps slider parameter values to CSS filter strings and applies them
 * to the preview image element in real-time (zero network latency).
 *
 * Parameter ranges:
 *   warmth     (-1..1)  →  sepia(0..0.6) + hue-rotate for cool tones
 *   brightness (-1..1)  →  brightness(0.5..1.5)
 *   blur        (0..1)  →  blur(0..10px)
 *   contrast   (-1..1)  →  contrast(0.5..1.5)
 *   saturation (-1..1)  →  saturate(0..2)
 *
 * License: MIT
 * Copyright (c) 2025 Seedance Wizard Contributors
 */

window.SeedanceFilters = (function () {
  "use strict";

  /**
   * Clamp a value to the given range.
   */
  function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
  }

  /**
   * Linear interpolation: map value from [inMin, inMax] to [outMin, outMax].
   */
  function lerp(val, inMin, inMax, outMin, outMax) {
    const t = clamp((val - inMin) / (inMax - inMin), 0, 1);
    return outMin + t * (outMax - outMin);
  }

  /**
   * Build a CSS filter string from the parameter object.
   *
   * @param {Object} params
   * @param {number} params.warmth     -1 (cool) to 1 (warm)
   * @param {number} params.brightness -1 (dark) to 1 (bright)
   * @param {number} params.blur       0 (sharp) to 1 (max blur)
   * @param {number} params.contrast   -1 (flat) to 1 (high contrast)
   * @param {number} params.saturation -1 (desaturated) to 1 (oversaturated)
   * @returns {string} CSS filter value (e.g. "sepia(0.3) brightness(1.2)")
   */
  function buildFilterString(params) {
    const filters = [];

    // Warmth: positive → sepia (warm), negative → hue-rotate toward blue (cool)
    const w = clamp(params.warmth ?? 0, -1, 1);
    if (w > 0) {
      filters.push("sepia(" + (w * 0.6).toFixed(3) + ")");
      filters.push("saturate(" + (1 + w * 0.3).toFixed(3) + ")");
    } else if (w < 0) {
      // Cool shift: rotate hue toward blue
      filters.push("hue-rotate(" + (w * 25).toFixed(1) + "deg)");
    }

    // Brightness: -1 → 0.5x, 0 → 1x, 1 → 1.5x
    const b = clamp(params.brightness ?? 0, -1, 1);
    const brightVal = lerp(b, -1, 1, 0.5, 1.5);
    if (Math.abs(brightVal - 1) > 0.005) {
      filters.push("brightness(" + brightVal.toFixed(3) + ")");
    }

    // Blur: 0 → 0px, 1 → 10px
    const bl = clamp(params.blur ?? 0, 0, 1);
    const blurPx = bl * 10;
    if (blurPx > 0.05) {
      filters.push("blur(" + blurPx.toFixed(1) + "px)");
    }

    // Contrast: -1 → 0.5x, 0 → 1x, 1 → 1.5x
    const c = clamp(params.contrast ?? 0, -1, 1);
    const contrastVal = lerp(c, -1, 1, 0.5, 1.5);
    if (Math.abs(contrastVal - 1) > 0.005) {
      filters.push("contrast(" + contrastVal.toFixed(3) + ")");
    }

    // Saturation: -1 → 0 (grayscale), 0 → 1x, 1 → 2x
    const s = clamp(params.saturation ?? 0, -1, 1);
    const saturateVal = lerp(s, -1, 1, 0, 2);
    if (Math.abs(saturateVal - 1) > 0.005) {
      filters.push("saturate(" + saturateVal.toFixed(3) + ")");
    }

    return filters.join(" ") || "none";
  }

  /**
   * Apply CSS filters to an image element.
   *
   * @param {HTMLImageElement} imageElement - The <img> element to filter
   * @param {Object} params - Filter parameters (see buildFilterString)
   */
  function applyFilters(imageElement, params) {
    if (!imageElement) return;
    const filterStr = buildFilterString(params);
    imageElement.style.filter = filterStr;
    imageElement.style.webkitFilter = filterStr;
  }

  /**
   * Remove all CSS filters from an image element.
   *
   * @param {HTMLImageElement} imageElement
   */
  function resetFilters(imageElement) {
    if (!imageElement) return;
    imageElement.style.filter = "none";
    imageElement.style.webkitFilter = "none";
  }

  /**
   * Get a human-readable description of the current filter parameters.
   * Useful for display or logging.
   *
   * @param {Object} params
   * @returns {string[]} Array of descriptions
   */
  function describeFilters(params) {
    const descriptions = [];
    const w = params.warmth ?? 0;
    const b = params.brightness ?? 0;
    const bl = params.blur ?? 0;
    const c = params.contrast ?? 0;
    const s = params.saturation ?? 0;

    if (w > 0.3) descriptions.push("Warm tone");
    else if (w < -0.3) descriptions.push("Cool tone");

    if (b > 0.3) descriptions.push("Bright");
    else if (b < -0.3) descriptions.push("Dark");

    if (bl > 0.2) descriptions.push("Blurred bg");

    if (c > 0.3) descriptions.push("High contrast");
    else if (c < -0.3) descriptions.push("Low contrast");

    if (s > 0.3) descriptions.push("Vivid");
    else if (s < -0.3) descriptions.push("Desaturated");

    return descriptions;
  }

  // ── Public API ──
  return {
    buildFilterString: buildFilterString,
    applyFilters: applyFilters,
    resetFilters: resetFilters,
    describeFilters: describeFilters,
  };
})();
