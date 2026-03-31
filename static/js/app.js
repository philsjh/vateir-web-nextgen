/* VATéir — Theme & UI System */

(function () {
  "use strict";

  // ─── Theme Management ──────────────────────────────────────────────
  const THEME_KEY = "vateir-theme";

  function getSystemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function getStoredTheme() {
    return localStorage.getItem(THEME_KEY) || "system";
  }

  function resolveTheme(preference) {
    if (preference === "system") return getSystemTheme();
    return preference;
  }

  function applyTheme(preference) {
    var resolved = resolveTheme(preference);
    var html = document.documentElement;
    html.classList.remove("light", "dark");
    html.classList.add(resolved);
    localStorage.setItem(THEME_KEY, preference);

    // Update toggle button states
    document.querySelectorAll("[data-theme-btn]").forEach(function (btn) {
      var isActive = btn.getAttribute("data-theme-btn") === preference;
      btn.classList.toggle("text-brand-400", isActive);
      btn.classList.toggle("bg-brand-500/10", isActive);
      btn.classList.toggle("text-white/40", !isActive);
    });

    // Update light-mode specific buttons
    document.querySelectorAll("[data-theme-btn]").forEach(function (btn) {
      if (resolved === "light") {
        btn.classList.remove("text-white/40");
        if (!btn.classList.contains("text-brand-400")) {
          btn.classList.add("text-gray-400");
        }
      } else {
        btn.classList.remove("text-gray-400");
      }
    });
  }

  // Apply immediately (before DOM ready) to prevent flash
  applyTheme(getStoredTheme());

  // Listen for system theme changes
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", function () {
      if (getStoredTheme() === "system") {
        applyTheme("system");
      }
    });

  // Bind theme toggle buttons on DOM ready
  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(getStoredTheme());

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-theme-btn]");
      if (btn) {
        applyTheme(btn.getAttribute("data-theme-btn"));
      }
    });
  });

  // ─── Page Loader ───────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    var loader = document.getElementById("page-loader");
    if (!loader) return;

    document.addEventListener("click", function (e) {
      var link = e.target.closest("a[href]");
      if (!link) return;
      var href = link.getAttribute("href");
      if (
        !href ||
        href.startsWith("#") ||
        href.startsWith("javascript:") ||
        link.target === "_blank" ||
        e.ctrlKey ||
        e.metaKey ||
        e.shiftKey
      )
        return;
      if (href === window.location.pathname) return;
      loader.classList.add("active");
      loader.classList.remove("done");
    });

    window.addEventListener("beforeunload", function () {
      loader.classList.add("done");
    });

    document.addEventListener("submit", function () {
      loader.classList.add("active");
      loader.classList.remove("done");
    });
  });

  // ─── Searchable Selects (Tom Select) ─────────────────────────────
  function initTomSelect(el) {
    if (typeof TomSelect === "undefined") return;
    // Skip if already initialized or has custom init (data-no-tomselect)
    if (el.tomselect || el.dataset.noTomselect) return;
    new TomSelect(el, {
      create: false,
      allowEmptyOption: true,
      controlInput: "<input>",
      dropdownParent: "body",
    });
  }

  function initAllSelects(root) {
    if (typeof TomSelect === "undefined") return;
    (root || document).querySelectorAll("select.glass-select").forEach(initTomSelect);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initAllSelects();

    // Watch for dynamically added selects
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          if (node.nodeType !== 1) return;
          if (node.matches && node.matches("select.glass-select")) {
            initTomSelect(node);
          }
          if (node.querySelectorAll) {
            node.querySelectorAll("select.glass-select").forEach(initTomSelect);
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });

  // Expose for external use
  window.VateirTheme = {
    apply: applyTheme,
    get: getStoredTheme,
    resolve: resolveTheme,
  };
})();
