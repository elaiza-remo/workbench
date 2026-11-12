// IDE-style editor tabs: every page you open becomes a tab, like files in VS Code.
// Tabs live in this browser's localStorage; nothing is sent to the server.
(function () {
  "use strict";

  // Tabs are kept per account, so the demo and your own account don't mix.
  var STORE_KEY = "workbench.tabs.v1." + (document.body.dataset.user || "anon");
  var MAX_TABS = 10;
  var body = document.body;
  var strip = document.getElementById("editor-tabs");
  if (!strip) return;

  var siteName = body.dataset.siteName || "";
  var section = body.dataset.section || "home";
  var noTab = body.dataset.noTab === "1";
  var here = location.pathname;
  var hereUrl = location.pathname + location.search;

  var KINDS = {
    home: { icon: "~", label: "" },
    prep: { icon: "#", label: "interview-prep" },
    journal: { icon: "{}", label: "projects" },
  };

  function pageTitle() {
    var t = document.title;
    var suffix = " · " + siteName;
    if (siteName && t.slice(-suffix.length) === suffix) t = t.slice(0, -suffix.length);
    return t.trim() || "untitled";
  }

  function load() {
    try {
      var raw = JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
      return Array.isArray(raw) ? raw.filter(function (t) { return t && t.path && t.url; }) : [];
    } catch (e) { return []; }
  }
  function save(tabs) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(tabs)); } catch (e) {}
  }

  var tabs = load();
  var activeIndex = tabs.findIndex(function (t) { return t.path === here; });

  if (!noTab) {
    var entry = { path: here, url: hereUrl, title: pageTitle(), kind: section, used: Date.now() };
    if (activeIndex >= 0) {
      tabs[activeIndex] = entry;
    } else {
      // Open next to the tab you came from, like an editor does.
      var from = -1;
      try { from = tabs.findIndex(function (t) { return t.path === sessionStorage.getItem("workbench.lastTab"); }); } catch (e) {}
      activeIndex = from >= 0 ? from + 1 : tabs.length;
      tabs.splice(activeIndex, 0, entry);
    }
    // Too many tabs: close the least recently used one (never the active tab).
    while (tabs.length > MAX_TABS) {
      var oldest = -1;
      tabs.forEach(function (t, i) {
        if (t.path !== here && (oldest < 0 || t.used < tabs[oldest].used)) oldest = i;
      });
      tabs.splice(oldest, 1);
    }
    activeIndex = tabs.findIndex(function (t) { return t.path === here; });
    save(tabs);
    try { sessionStorage.setItem("workbench.lastTab", here); } catch (e) {}
  }

  function closeTab(path) {
    var i = tabs.findIndex(function (t) { return t.path === path; });
    if (i < 0) return;
    var wasActive = tabs[i].path === here;
    tabs.splice(i, 1);
    save(tabs);
    if (wasActive) {
      var next = tabs[i] || tabs[i - 1];
      location.href = next ? next.url : "/";
    } else {
      render();
    }
  }

  function render() {
    strip.textContent = "";
    tabs.forEach(function (t) {
      var kind = KINDS[t.kind] || KINDS.home;
      var a = document.createElement("a");
      a.className = "editor-tab kind-" + t.kind + (t.path === here ? " is-active" : "");
      a.href = t.url;
      a.title = t.title;
      a.setAttribute("role", "tab");
      a.setAttribute("aria-selected", t.path === here ? "true" : "false");
      if (t.path === here) a.setAttribute("aria-current", "page");

      var icon = document.createElement("span");
      icon.className = "tab-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = kind.icon;

      var label = document.createElement("span");
      label.className = "tab-title";
      label.textContent = t.title;

      var close = document.createElement("button");
      close.type = "button";
      close.className = "tab-close";
      close.setAttribute("aria-label", "Close " + t.title);
      close.textContent = "×";
      close.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeTab(t.path);
      });

      a.addEventListener("auxclick", function (e) {
        if (e.button === 1) { e.preventDefault(); closeTab(t.path); }
      });
      a.append(icon, label, close);
      strip.appendChild(a);
    });
    var active = strip.querySelector(".is-active");
    if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  // Breadcrumb path under the tabs: workbench › projects › eFit
  var crumbs = document.getElementById("editor-path");
  if (crumbs) {
    var parts = [siteName.toLowerCase() || "home"];
    if (KINDS[section] && KINDS[section].label) parts.push(KINDS[section].label);
    if (section !== "home" || pageTitle().toLowerCase() !== "home") parts.push(pageTitle());
    crumbs.textContent = "";
    parts.forEach(function (p, i) {
      if (i) {
        var sep = document.createElement("span");
        sep.className = "path-sep";
        sep.textContent = "›";
        crumbs.appendChild(sep);
      }
      var s = document.createElement("span");
      s.textContent = p;
      if (i === parts.length - 1) s.className = "path-current";
      crumbs.appendChild(s);
    });
  }

  // Unsaved-changes dot on the active tab while you edit a form, like a modified file.
  document.querySelectorAll("main form[method=post], main form[method=POST]").forEach(function (form) {
    if (form.dataset.closesTab !== undefined) return;
    form.addEventListener("input", function () {
      var active = strip.querySelector(".is-active");
      if (active) active.classList.add("is-modified");
    });
    form.addEventListener("submit", function () {
      var active = strip.querySelector(".is-active");
      if (active) active.classList.remove("is-modified");
    });
  });

  // Deleting something closes its tab.
  document.querySelectorAll("form[data-closes-tab]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var target = form.dataset.closesTab;
      tabs = tabs.filter(function (t) { return t.path.indexOf(target) !== 0; });
      save(tabs);
    });
  });

  render();
})();
