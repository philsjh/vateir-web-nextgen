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

  // ─── Mobile Sidebar Toggle ──────────────────────────────────────
  document.addEventListener("click", function (e) {
    var openBtn = e.target.closest("[data-open-sidebar]");
    if (openBtn) {
      var id = openBtn.getAttribute("data-open-sidebar");
      var sidebar = document.getElementById(id);
      var backdrop = document.getElementById(id + "-backdrop");
      if (sidebar) sidebar.classList.remove("-translate-x-full");
      if (backdrop) backdrop.classList.remove("hidden");
      document.body.classList.add("overflow-hidden");
      return;
    }
    var closeBtn = e.target.closest("[data-close-sidebar]");
    if (closeBtn) {
      var id = closeBtn.getAttribute("data-close-sidebar");
      var sidebar = document.getElementById(id);
      var backdrop = document.getElementById(id + "-backdrop");
      if (sidebar) sidebar.classList.add("-translate-x-full");
      if (backdrop) backdrop.classList.add("hidden");
      document.body.classList.remove("overflow-hidden");
    }
  });
  // Escape closes any open sidebar
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document
        .querySelectorAll("[id$='-sidebar']:not(.translate-x-0)")
        .forEach(function (el) {
          el.classList.add("-translate-x-full");
        });
      document
        .querySelectorAll("[id$='-sidebar-backdrop']")
        .forEach(function (el) {
          el.classList.add("hidden");
        });
      document.body.classList.remove("overflow-hidden");
      // Also close mobile nav
      var mobileMenu = document.getElementById("mobile-nav-menu");
      if (mobileMenu) mobileMenu.classList.add("hidden");
    }
  });

  // ─── Mobile Nav Toggle ─────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.getElementById("mobile-nav-toggle");
    var menu = document.getElementById("mobile-nav-menu");
    if (toggle && menu) {
      toggle.addEventListener("click", function () {
        menu.classList.toggle("hidden");
      });
    }
  });

  // Expose for external use
  window.VateirTheme = {
    apply: applyTheme,
    get: getStoredTheme,
    resolve: resolveTheme,
  };
})();
