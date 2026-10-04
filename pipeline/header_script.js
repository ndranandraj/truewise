/* The site header's inline script. Source of truth: head() in build_college_pages.py inserts it with
 * comments stripped, and pipeline/sync_header.py copies that header into the hand-written pages.
 *
 * 1. Today's behaviour: Escape closes the open menu (focus back on its button); a click outside
 *    closes it; simple data tables get their column names for the phone card layout.
 * 2. Enlarged text (October 2026 review): at 200% text the header row no longer fits. A width
 *    breakpoint cannot know when items collide, so this measures and stops at the first step that
 *    fits: today's header, then the tagline hidden (.hdr-tight), then the links in the menu
 *    (.hdr-collapsed), then the row wrapping (.hdr-wrap). Text is never made smaller. "Fits" means
 *    what a reader sees: the items sit side by side without overlapping and end inside the screen.
 * 3. Pinning, switched on only once measured (html.pin-ok; without this script nothing pins): a
 *    header taller than a quarter of the screen, or one that with a pinned section bar would cover
 *    more than 35%, scrolls away; a bar or rail too tall for the screen scrolls too. Bars pin below
 *    the header's real height (--hdr-h), and anchors, the skip link and focus clear everything
 *    pinned (--pin-h, used by scroll-padding-top).
 * 4. Focus: if the focused header item is hidden by a collapse (or the open menu by an expand),
 *    focus moves to its visible counterpart instead of falling to <body>. A focused menu link is
 *    scrolled fully into view, instantly (the site's smooth scrolling left it half off-screen).
 * Runs where it stands, at the end of the header, so the header is set before the page paints. */
(function () {
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var d = document.querySelector(".nav-toggle[open]");
    if (d) { d.open = false; d.querySelector("summary").focus(); }
  });
  document.addEventListener("click", function (e) {
    var d = document.querySelector(".nav-toggle[open]");
    if (d && !d.contains(e.target)) d.open = false;
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table.t").forEach(function (t) {
      var h = [].map.call(t.querySelectorAll("thead th"), function (x) { return x.textContent.trim(); });
      if (!h.length) return;
      t.querySelectorAll("tbody tr").forEach(function (r) {
        [].forEach.call(r.children, function (c, i) { if (h[i]) c.setAttribute("data-label", h[i]); });
      });
      t.classList.add("stack");
    });
  });

  var root = document.documentElement;
  var header = document.querySelector(".site-header");
  if (!header) return;
  var row = header.querySelector(".wrap");
  var nav = header.querySelector("nav");
  var brand = header.querySelector(".brand");
  var tagline = header.querySelector(".brand-tagline");
  var toggle = header.querySelector(".nav-toggle");
  if (!row || !nav || !brand) return;
  header.classList.add("hdr-js");

  function shown(e) {
    if (!e) return false;
    var r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden";
  }
  function fits() {
    var items = [brand];
    if (shown(tagline)) items.push(tagline);
    [].forEach.call(nav.children, function (e) { if (shown(e)) items.push(e); });
    var edge = root.clientWidth, prev = -Infinity;
    for (var i = 0; i < items.length; i++) {
      var r = items[i].getBoundingClientRect();
      if (r.left < prev - 1 || r.right > edge + 1) return false;
      prev = r.right;
    }
    return true;
  }

  var lastFocused = null;
  header.addEventListener("focusin", function (e) {
    lastFocused = e.target;
    if (e.target.closest && e.target.closest(".menu")) {
      e.target.scrollIntoView({ block: "nearest", behavior: "instant" });
    }
  });
  function forget(e) { if (!header.contains(e.target)) lastFocused = null; }
  document.addEventListener("focusin", forget);
  document.addEventListener("pointerdown", forget);
  function focusedItem() {
    var a = document.activeElement;
    if (a && header.contains(a)) return a;
    if ((!a || a === document.body) && lastFocused && header.contains(lastFocused)) return lastFocused;
    return null;
  }
  function restoreFocus(was) {
    if (!was || shown(was)) return;
    var href = was.getAttribute && was.getAttribute("href");
    var summary = toggle && toggle.querySelector("summary");
    var twin = href && [].find.call(nav.querySelectorAll(":scope > a"), function (a) {
      return a.getAttribute("href") === href && shown(a);
    });
    if (twin) { twin.focus(); return; }
    if (summary && shown(summary)) { summary.focus(); return; }
    var cta = nav.querySelector(".nav-cta");
    if (cta && shown(cta)) cta.focus();
  }

  var STEPS = ["hdr-tight", "hdr-collapsed", "hdr-wrap"];
  function update() {
    var was = focusedItem();
    header.classList.remove.apply(header.classList, STEPS.concat("hdr-unstick"));
    for (var i = 0; i < STEPS.length && !fits(); i++) header.classList.add(STEPS[i]);
    if (toggle && toggle.open && !shown(toggle.querySelector("summary"))) toggle.open = false;

    var vh = window.innerHeight;
    var h = header.getBoundingClientRect().height;
    root.classList.add("pin-ok");
    var bars = [].filter.call(document.querySelectorAll(".sectnav, .subnav"), function (n) {
      n.classList.remove("pin-off");
      return getComputedStyle(n).position === "sticky" && n.getBoundingClientRect().height > 0;
    });
    var barH = bars.reduce(function (m, n) { return Math.max(m, n.getBoundingClientRect().height); }, 0);
    if (h > vh / 4 || h + barH > vh * 0.35) header.classList.add("hdr-unstick");
    var barPinned = 0;
    bars.forEach(function (n) {
      var bh = n.getBoundingClientRect().height;
      if (bh > vh / 4) n.classList.add("pin-off"); else barPinned = Math.max(barPinned, bh);
    });
    var hdrPinned = header.classList.contains("hdr-unstick") ? 0 : Math.round(h);
    [].forEach.call(document.querySelectorAll(".rail__inner"), function (r) {
      r.classList.remove("pin-off");
      if (getComputedStyle(r).position !== "sticky") return;
      var top = parseFloat(getComputedStyle(r).top) || 0;
      if (r.getBoundingClientRect().height + top > vh) r.classList.add("pin-off");
    });
    root.style.setProperty("--hdr-h", hdrPinned + "px");
    root.style.setProperty("--pin-h", Math.round(hdrPinned + barPinned) + "px");
    restoreFocus(was);
  }

  update();
  // Section bars and the rail come after the header in the page, so check again once they exist.
  document.addEventListener("DOMContentLoaded", update);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(update);
  var last = "";
  function onResize() {
    var key = row.clientWidth + ":" + window.innerHeight + ":" + Math.round(brand.getBoundingClientRect().height);
    if (key !== last) { last = key; update(); }
  }
  if ("ResizeObserver" in window) {
    new ResizeObserver(onResize).observe(row);
    new ResizeObserver(onResize).observe(brand);
  }
  window.addEventListener("resize", onResize);
})();
