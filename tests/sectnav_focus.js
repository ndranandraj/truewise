#!/usr/bin/env node
/* The section links, by keyboard (October and November 2026).
 *
 *   node tests/sectnav_focus.js              against the built site/
 *   node tests/sectnav_focus.js --site DIR   against another built tree
 *   node tests/sectnav_focus.js --out DIR    results directory (default sectnav-focus-<stamp>/)
 *   --only browser=firefox-200,width=320,mode=js,page=profile-ucla,sequence=edge+resize   a subset
 *
 * python -m tests.build_sectnav_fixture builds just the two pages this needs, so it can run on a pull
 * request with nothing published.
 *
 * On phones the finding's and every profile's section links run sideways under a 36px fade. Measured
 * in Chromium and Firefox, moving focus takes no account of the fade (review of 11 October: 3 of the
 * finding's 7 links at each phone width, and UCLA's Sources link at 200% text) or of an outline drawn
 * outside the link's box (review of 5 November: a border 1px above the screen's bottom edge left the
 * ring 3px past it). Firefox also leaves a link partly past the edge unless its scroll margin is large
 * enough (measured 5 November: cut by up to 5.5px with 12px, or 12px at 200% text).
 * The fix has three parts, and this checks each:
 *   - with the script, the row scrolls each focused link clear of the fade and the edges, again when
 *     the row or the link changes size, and only for a link that has focus;
 *   - without it (JavaScript off, or the script failing), the links wrap and nothing is hidden;
 *   - the link has the scroll margin to come fully on screen and its focus ring is painted inside it,
 *     so whatever shows the link shows the whole ring.
 *
 * Six sequences, in Chromium and Firefox, at normal text and at Firefox's native 200% text, with
 * reduced motion, with JavaScript off and with the script made to fail:
 *   walk       every link by real Tab, then back by real Shift+Tab, at a person's pace
 *   rapid      Tab out of the last link and Shift+Tab back after 0, 50 and 100ms
 *   edge       a link placed just past the bottom or top edge (12, 5 and 1px) or just inside it (1 and
 *              3px), then reached by key. No DOM is changed: at the top of a page, a shorter screen
 *              puts the link at its bottom edge
 *   resize     focus kept on a link while the screen changes width
 *   reflow     focus kept on a link while its text grows, with and without the row changing size
 *   elsewhere  focus outside the bar, or the row swiped by hand: the script must leave both alone
 *
 * A resize or reflow judges the link across the screen. It does not judge the page's vertical position
 * afterwards: the page does not follow focus when text reflows, on this bar or on any other link, and
 * the script must not pull it back. Whether the link ended up off screen vertically is recorded in
 * each such observation and counted in the summary.
 *
 * Like the layout check, it does not report a pass it has not earned: a page that does not load, a
 * bar that is missing, text that was not enlarged, a link that could not be placed, a ring that could
 * not be read, or a run with no observations is a failure.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const http = require("http");

let chromium, firefox;
try {
  ({ chromium, firefox } = require("playwright"));
} catch (_) {
  console.error("playwright is not installed: npm install && npx playwright install chromium firefox");
  process.exit(2);
}

const args = process.argv.slice(2);
const valueOf = (n) => { const i = args.indexOf(n); return i === -1 ? null : args[i + 1]; };
const SITE = path.resolve(valueOf("--site") || path.join(__dirname, "..", "site"));
const OUT = path.resolve(valueOf("--out") || `sectnav-focus-${new Date().toISOString().replace(/[:.]/g, "-")}`);

const only = Object.fromEntries((valueOf("--only") || "").split(",").filter(Boolean).map((kv) => kv.split("=")));
const pick = (list, key) => list.filter((x) => !only[key] || only[key] === x.label);

const PAGES = [
  { label: "finding-fvtge", path: "/findings/fvtge-reporting/" },
  { label: "profile-ucla", path: "/college/university-of-california-los-angeles/" },
];
const WIDTHS = [
  { label: "320", width: 320, height: 700, phone: true },
  { label: "390", width: 390, height: 844, phone: true },
  { label: "768", width: 768, height: 1024, phone: false },
];
const MADE_TO_FAIL = "sectnav_focus: the section script was made to fail";
const MODES = [
  { label: "js", js: true },
  { label: "reduced-motion", js: true, reducedMotion: "reduce" },
  { label: "js-off", js: false },
  // The section script is rewritten to throw on its first line (other scripts untouched): a failed
  // enhancement must leave the unenhanced layout.
  { label: "script-fails", js: true, breakScript: true },
];
const BROWSERS = [
  { label: "chromium", type: () => chromium, opts: {} },
  { label: "firefox", type: () => firefox, opts: {} },
  { label: "firefox-200", type: () => firefox, enlarged: true,
    opts: { firefoxUserPrefs: { "ui.textScaleFactor": 200, "browser.display.os-zoom-behavior": 2 } } },
];
const SEQUENCES = ["walk", "rapid", "edge", "resize", "reflow", "elsewhere"];
const wanted = (only.sequence || SEQUENCES.join("+")).split("+");
const RAPID_GAPS = [0, 50, 100];
const EDGE_GAPS = [-12, -5, -1, 1, 3]; // negative: that much of the link is past the edge
const edgeWords = (px) => `${Math.abs(px).toFixed(1)}px ${px < 0 ? "past" : "clear"}`;
// Where a resize goes from each starting width. Narrowing a phone is checked on every link; the rest
// on the last, which has the furthest to travel.
const RESIZES = { 320: [390, 768], 390: [320], 768: [320] };
const REFLOWS = [
  { label: "wider letters", css: ".sectnav a { letter-spacing: 0.35em; }" }, // the link grows, the row does not
  { label: "larger text", css: ".sectnav a { font-size: 1.5em; }" }, // the link and the row both grow
];

const MIME = { ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".png": "image/png", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".csv": "text/csv; charset=utf-8" };

function serve(dir) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let file = path.join(dir, decodeURIComponent(req.url.split("?")[0]));
      try {
        if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
        if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
        res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
        fs.createReadStream(file).pipe(res);
      } catch (e) { res.writeHead(500); res.end(String(e)); }
    });
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

/* Runs in the page: where the focused link and its ring are, against everything that can hide them. */
function measure() {
  const nav = document.querySelector(".sectnav");
  const links = nav ? [...nav.querySelectorAll("a")] : [];
  const a = document.activeElement;
  const index = links.indexOf(a);
  if (index < 0) return { index, tag: a ? a.tagName : null };
  const cs = getComputedStyle(a);
  // An outline starts at the border edge plus its offset and runs outward for its width. A ring
  // painted inside the link therefore reaches nothing outside the box, and is still a ring.
  const ringWidth = cs.outlineStyle === "none" ? 0 : parseFloat(cs.outlineWidth) || 0;
  const offset = parseFloat(cs.outlineOffset) || 0;
  const reach = ringWidth ? Math.max(0, ringWidth + offset) : 0;
  const inset = ringWidth ? Math.max(0, -offset) : 0;
  const r = a.getBoundingClientRect();
  const box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
  const ring = { left: r.left - reach, right: r.right + reach, top: r.top - reach, bottom: r.bottom + reach };
  // The ring's inner edge must stay at least 1px clear of the words, and the ring must show against
  // the chip.
  const range = document.createRange();
  range.selectNodeContents(a);
  const t = range.getBoundingClientRect();
  const clear = inset + 1;
  const ringOverText = !!inset && (t.left < r.left + clear || t.right > r.right - clear || t.top < r.top + clear || t.bottom > r.bottom - clear);
  const rgb = (c) => {
    const m = /^rgba?\(([^)]+)\)$/.exec(c);
    if (!m) return null;
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return p.length === 3 || p[3] === 1 ? p.slice(0, 3) : null;
  };
  const lum = (p) => {
    const [x, y, z] = p.map((v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * x + 0.7152 * y + 0.0722 * z;
  };
  const fg = rgb(cs.outlineColor), bg = rgb(cs.backgroundColor);
  const contrast = fg && bg ? (Math.max(lum(fg), lum(bg)) + 0.05) / (Math.min(lum(fg), lum(bg)) + 0.05) : null;
  // Every ancestor that clips (overflow other than visible) cuts at its visible area: the padding
  // box less any scrollbar, which is clientLeft/Top plus clientWidth/Height.
  const clips = [];
  for (let el = a.parentElement; el && el !== document.documentElement; el = el.parentElement) {
    const o = getComputedStyle(el);
    if (o.overflowX !== "visible" || o.overflowY !== "visible") {
      const b = el.getBoundingClientRect();
      clips.push({ tag: el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(" ")[0] : ""),
        left: b.left + el.clientLeft, top: b.top + el.clientTop,
        right: b.left + el.clientLeft + el.clientWidth, bottom: b.top + el.clientTop + el.clientHeight });
    }
  }
  clips.push({ tag: "viewport", left: 0, top: 0, right: document.documentElement.clientWidth, bottom: window.innerHeight });
  // The fade: the scroll wrapper's ::after, where it is drawn.
  let fade = null;
  const wrap = nav.querySelector(".sectnav__scroll");
  if (wrap) {
    const f = getComputedStyle(wrap, "::after");
    if (f.content !== "none" && f.display !== "none" && parseFloat(f.width) > 0) {
      const w = wrap.getBoundingClientRect();
      fade = { left: w.right - (parseFloat(f.right) || 0) - parseFloat(f.width), right: w.right - (parseFloat(f.right) || 0),
        top: w.top + (parseFloat(f.top) || 0), bottom: w.bottom - (parseFloat(f.bottom) || 0) };
    }
  }
  // A pinned header covers what scrolls under it.
  const hdr = document.querySelector(".site-header");
  const hp = hdr && getComputedStyle(hdr).position;
  const header = hdr && (hp === "sticky" || hp === "fixed") ? hdr.getBoundingClientRect().bottom : null;
  const ul = nav.querySelector("ul");
  return { index, count: links.length, text: a.textContent.trim(), ringWidth, reach, inset, ringOverText, contrast, box, ring, clips, fade, header,
    navInHeader: !!(hdr && hdr.contains(nav)), scrollLeft: ul ? ul.scrollLeft : null, scrollY: window.scrollY, viewport: { width: window.innerWidth, height: window.innerHeight } };
}

function navState() {
  const nav = document.querySelector(".sectnav");
  if (!nav) return { present: false };
  const ul = nav.querySelector("ul");
  const s = getComputedStyle(nav);
  return { present: true, shown: s.display !== "none" && nav.getBoundingClientRect().height > 0,
    enhanced: nav.classList.contains("sectnav--scroll"), position: s.position,
    scrolls: !!ul && getComputedStyle(ul).overflowX !== "visible", wraps: !!ul && getComputedStyle(ul).flexWrap === "wrap",
    links: nav.querySelectorAll("a").length, body: parseFloat(getComputedStyle(document.body).fontSize),
    pageWider: document.documentElement.scrollWidth > document.documentElement.clientWidth };
}

/** Wait until the focused link, the row's scroll and the page's scroll stop moving, up to 1.5s.
 *  Reading too early once called a moving page clean. The waiting is done here, not in the page: with
 *  JavaScript off the page's own timers never fire. */
async function settled(page) {
  const key = () => {
    const a = document.activeElement, ul = document.querySelector(".sectnav ul");
    const r = a ? a.getBoundingClientRect() : { left: 0, top: 0 };
    return [r.left, r.top, ul ? ul.scrollLeft : 0, window.scrollY].map((v) => Math.round(v * 10)).join(",");
  };
  const t0 = Date.now();
  let last = "", same = 0;
  while (same < 4 && Date.now() - t0 < 1500) {
    const k = await page.evaluate(key);
    same = k === last ? same + 1 : 0;
    last = k;
    await page.waitForTimeout(16);
  }
  return Date.now() - t0;
}

const EPS = 0.5;
const fmt = (b) => `${b.left.toFixed(1)}..${b.right.toFixed(1)} x ${b.top.toFixed(1)}..${b.bottom.toFixed(1)}`;

/** Everything that hides the link or its ring. `acrossOnly` leaves out the page's vertical position,
 *  which a resize or reflow does not promise (see the top of this file). */
function judge(m, ctx, phase, acrossOnly) {
  const out = [];
  const at = `${ctx} ${phase} link ${m.index + 1}/${m.count} "${m.text}"`;
  for (const what of ["box", "ring"]) {
    const g = m[what];
    for (const c of m.clips) {
      const cut = [g.left < c.left - EPS && "left", g.right > c.right + EPS && "right",
        !acrossOnly && g.top < c.top - EPS && "top", !acrossOnly && g.bottom > c.bottom + EPS && "bottom"].filter(Boolean);
      if (cut.length) out.push({ kind: `${what}-clipped`, detail: `${at}: ${what === "ring" ? "focus ring" : "link"} cut at the ${cut.join(" and ")} of ${c.tag} (${what} ${fmt(g)}, visible ${fmt(c)})` });
    }
    if (m.fade && g.right > m.fade.left + EPS && g.left < m.fade.right && g.bottom > m.fade.top && g.top < m.fade.bottom) {
      out.push({ kind: `${what}-under-fade`, detail: `${at}: ${what === "ring" ? "focus ring" : "link"} reaches ${(g.right - m.fade.left).toFixed(1)}px into the fade (fade from ${m.fade.left.toFixed(1)}px)` });
    }
    if (!acrossOnly && m.header != null && !m.navInHeader && g.top < m.header - EPS) {
      out.push({ kind: `${what}-under-header`, detail: `${at}: ${what === "ring" ? "focus ring" : "link"} top ${g.top.toFixed(1)}px is under the pinned header (to ${m.header.toFixed(1)}px)` });
    }
  }
  if (!m.ringWidth) out.push({ kind: "no-focus-ring", detail: `${at}: the focused link shows no outline` });
  else if (m.contrast == null) out.push({ kind: "ring-contrast-unread", detail: `${at}: could not read the ring and chip colours` });
  else if (m.contrast < 3) out.push({ kind: "ring-contrast", detail: `${at}: the ring has ${m.contrast.toFixed(2)}:1 against the chip` });
  if (m.ringOverText) out.push({ kind: "ring-over-text", detail: `${at}: the ring painted inside the link is within 1px of its words` });
  return out;
}

/** What a sequence shares: read the focused link, judge it, keep the observation. */
function observer(page, ctx) {
  const findings = [], obs = [];
  let sequence = "walk";
  const add = (f) => findings.push({ sequence, ...f });
  return {
    findings, obs, add,
    start: (s) => { sequence = s; },
    expect: async (want, phase, { acrossOnly = false, early = false } = {}) => {
      await page.waitForTimeout(50);
      const soon = await page.evaluate(measure);
      const waited = await settled(page);
      const m = await page.evaluate(measure);
      if (m.index !== want) {
        obs.push({ sequence, phase, want, waitedMs: Math.round(waited), ...m });
        add({ kind: "wrong-focus", detail: `${ctx} ${phase}: expected link ${want + 1} focused, found ${m.index < 0 ? m.tag : "link " + (m.index + 1)}` });
        return;
      }
      // Anything the browser or the script does late is measured once more, 1.3s on, and only what
      // remains is reported; both readings are recorded.
      let got = judge(m, ctx, phase, acrossOnly), final = m, first = null;
      if (got.length) {
        await page.waitForTimeout(1300);
        final = await page.evaluate(measure);
        first = { findings: got.map((f) => f.kind), box: m.box, scrollY: m.scrollY };
        got = final.index === want ? judge(final, ctx, phase, acrossOnly) : [{ kind: "wrong-focus", detail: `${ctx} ${phase}: focus moved on its own` }];
      }
      const offScreenVertically = acrossOnly ? final.ring.top < 0 || final.ring.bottom > final.viewport.height : undefined;
      obs.push({ sequence, phase, want, waitedMs: Math.round(waited), ...final, firstReading: first, offScreenVertically });
      got.forEach(add);
      // With reduced motion nothing may animate into place: 50ms after the key, the link is where it
      // ends up. (The page's own frames cannot be awaited here: with JavaScript off they never run.)
      if (early && soon.index === want) judge(soon, ctx, `${phase} (50ms after the key)`, acrossOnly).forEach(add);
    },
  };
}

const focusLink = (page, i) => page.evaluate((j) => document.querySelectorAll(".sectnav a")[j].focus({ preventScroll: true }), i);
async function reachLink(page, i) {
  // Focus is cleared first: focusing a link that already has focus does not scroll it into view.
  await page.evaluate(() => {
    if (document.activeElement) document.activeElement.blur();
    window.scrollTo(0, 0);
    document.querySelector(".sectnav a").focus();
  });
  for (let k = 0; k < i; k++) await page.keyboard.press("Tab");
}
const linkCount = (page) => page.evaluate(() => document.querySelectorAll(".sectnav a").length);

async function walk(page, on, reduced) {
  const n = await linkCount(page);
  // Enter the row by keyboard: from the element before the first link, Tab. Firefox makes the
  // scrolling list itself a Tab stop (native behaviour, kept), so that element may be the list.
  await page.evaluate(() => document.querySelector(".sectnav a").focus());
  await page.keyboard.press("Shift+Tab");
  const before = await page.evaluate(() => {
    const a = document.activeElement;
    return !a.closest(".sectnav a") ? (a.matches(".sectnav ul") ? "the list" : a.tagName) : null;
  });
  if (!before) on.add({ kind: "walk-setup", detail: `${on.ctx}: Shift+Tab from the first link stayed on a link` });
  await page.keyboard.press("Tab");
  await on.expect(0, "forward", { early: reduced });
  for (let i = 1; i < n; i++) { await page.keyboard.press("Tab"); await on.expect(i, "forward", { early: reduced }); }
  // Leave past the last link, pause as a person would, come back and walk to the first. Quick keys
  // have their own sequence below.
  await page.keyboard.press("Tab");
  await page.waitForTimeout(1500);
  await page.keyboard.press("Shift+Tab");
  await on.expect(n - 1, "reverse", { early: reduced });
  for (let i = n - 2; i >= 0; i--) { await page.keyboard.press("Shift+Tab"); await on.expect(i, "reverse", { early: reduced }); }
  return before;
}

async function rapid(page, on) {
  const n = await linkCount(page);
  for (const gap of RAPID_GAPS) {
    await reachLink(page, n - 1);
    await settled(page);
    await page.keyboard.press("Tab");
    if (gap) await page.waitForTimeout(gap);
    await page.keyboard.press("Shift+Tab");
    await on.expect(n - 1, `rapid, back after ${gap}ms`);
  }
}

/** Link i with its border `gap` px above the screen's bottom edge, or null if that could not be done.
 *  Near the top of a page the screen is made shorter; further down, the page is scrolled. */
async function placeAtBottom(page, w, i, gap) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.setViewportSize({ width: w.width, height: w.height });
    await page.evaluate(() => window.scrollTo(0, 0));
    const bottom = await page.evaluate((j) => document.querySelectorAll(".sectnav a")[j].getBoundingClientRect().bottom, i);
    if (bottom + gap < w.height) await page.setViewportSize({ width: w.width, height: Math.ceil(bottom + gap) });
    else await page.evaluate(([b, g]) => window.scrollTo(0, b + g - window.innerHeight), [bottom, gap]);
    await page.waitForTimeout(50);
    const got = await page.evaluate((j) => window.innerHeight - document.querySelectorAll(".sectnav a")[j].getBoundingClientRect().bottom, i);
    if (got >= gap - 0.5 && got < gap + 1.5) return got;
  }
  return null;
}

/** Link i with its border `gap` px below the screen's top edge or the pinned header. A pinned row cannot
 *  be placed (it sits where it pins), so it is measured where it is; `pinned` says so. */
async function placeAtTop(page, i, gap) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const got = await page.evaluate(([j, g]) => {
      const link = document.querySelectorAll(".sectnav a")[j];
      const hdr = document.querySelector(".site-header");
      const hp = hdr && getComputedStyle(hdr).position;
      const edge = () => (hdr && (hp === "sticky" || hp === "fixed") ? hdr.getBoundingClientRect().bottom : 0);
      window.scrollBy(0, link.getBoundingClientRect().top - edge() - g);
      return { gap: link.getBoundingClientRect().top - edge(), pinned: getComputedStyle(document.querySelector(".sectnav")).position === "sticky" };
    }, [i, gap]);
    if (got.pinned || (got.gap >= gap - 0.5 && got.gap < gap + 1.5)) return got;
    await page.waitForTimeout(50);
  }
  return null;
}

async function edge(page, on, w, ctx) {
  const n = await linkCount(page);
  for (const gap of EDGE_GAPS) {
    await focusLink(page, n - 2);
    const placed = await placeAtBottom(page, w, n - 1, gap);
    if (placed == null) on.add({ kind: "edge-setup", detail: `${ctx}: could not place the last link ${gap}px above the bottom edge, so it was not measured` });
    else {
      await page.keyboard.press("Tab");
      await on.expect(n - 1, `bottom edge, ${edgeWords(placed)}`);
    }
    await page.setViewportSize({ width: w.width, height: w.height });
    await focusLink(page, 1);
    const top = await placeAtTop(page, 0, gap);
    if (top == null) on.add({ kind: "edge-setup", detail: `${ctx}: could not place the first link ${gap}px below the top edge, so it was not measured` });
    else {
      await page.keyboard.press("Shift+Tab");
      await on.expect(0, top.pinned ? "top edge, pinned row" : `top edge, ${edgeWords(top.gap)}`);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
  }
}

async function resize(page, on, w) {
  const n = await linkCount(page);
  for (const to of RESIZES[w.label]) {
    const targets = w.label === "390" && to === 320 ? [...Array(n).keys()] : [n - 1];
    for (const i of targets) {
      await page.setViewportSize({ width: w.width, height: w.height });
      await reachLink(page, i);
      await on.expect(i, `before resizing ${w.width} to ${to}`);
      await page.setViewportSize({ width: to, height: w.height });
      await page.waitForTimeout(100);
      await on.expect(i, `focus kept, resized ${w.width} to ${to}`, { acrossOnly: true });
    }
    // Part way down the page, the row is pinned under the header (a phone turned while reading). It
    // stays pinned, so here the whole check applies, up and down as well as across.
    const pinnable = () => page.evaluate(() => getComputedStyle(document.querySelector(".sectnav")).position === "sticky");
    await page.setViewportSize({ width: w.width, height: w.height });
    await page.setViewportSize({ width: to, height: w.height });
    const toPinnable = await pinnable();
    await page.setViewportSize({ width: w.width, height: w.height });
    if (toPinnable && (await pinnable())) {
      await focusLink(page, n - 2);
      await page.evaluate(() => window.scrollTo(0, document.querySelector(".sectnav").getBoundingClientRect().bottom + window.scrollY + 600));
      await page.keyboard.press("Tab");
      await on.expect(n - 1, `pinned, before resizing ${w.width} to ${to}`);
      await page.setViewportSize({ width: to, height: w.height });
      await page.waitForTimeout(100);
      await on.expect(n - 1, `pinned, focus kept, resized ${w.width} to ${to}`);
    }
  }
  await page.setViewportSize({ width: w.width, height: w.height });
  await page.evaluate(() => window.scrollTo(0, 0));
}

const withStyle = (page, css) => page.evaluate((text) => { const s = document.createElement("style"); s.id = "sectnav-focus-probe"; s.textContent = text; document.head.append(s); }, css);
const dropStyle = (page) => page.evaluate(() => { const s = document.getElementById("sectnav-focus-probe"); if (s) s.remove(); });

async function reflow(page, on) {
  const n = await linkCount(page);
  for (const probe of REFLOWS) {
    await reachLink(page, n - 1);
    await on.expect(n - 1, `before ${probe.label}`);
    await withStyle(page, probe.css);
    await page.waitForTimeout(100);
    await on.expect(n - 1, `focus kept, ${probe.label}`, { acrossOnly: true });
    await dropStyle(page);
    await page.waitForTimeout(50);
  }
}

/** The script may only act for a section link that has focus, and only when a size changed. */
async function elsewhere(page, on, w, ctx) {
  const n = await linkCount(page);
  const row = () => page.evaluate(() => {
    const a = document.activeElement, ul = document.querySelector(".sectnav ul");
    return { inBar: !!(a && a.closest(".sectnav a")), scrollLeft: ul.scrollLeft, max: ul.scrollWidth - ul.clientWidth };
  });
  const setRow = (x) => page.evaluate((v) => { document.querySelector(".sectnav ul").scrollLeft = v; }, x);
  const record = (phase, before, after, kept) => {
    on.obs.push({ sequence: "elsewhere", phase, before, after });
    if (!kept) on.add({ kind: "script-interfered", detail: `${ctx} ${phase}: the row moved from ${before.scrollLeft} to ${after.scrollLeft} (focus in the bar: ${after.inBar})` });
  };

  // Focus outside the bar: a resize and a reflow must leave the row where it is.
  await reachLink(page, n - 1);
  await page.keyboard.press("Tab");
  await page.waitForTimeout(100);
  let state = await row();
  if (state.inBar) { on.add({ kind: "elsewhere-setup", detail: `${ctx}: Tab past the last link stayed in the bar` }); return; }
  await setRow(17);
  const before = await row();
  if (before.scrollLeft < 1) on.obs.push({ sequence: "elsewhere", phase: "focus elsewhere", notApplicable: "the row does not overflow at this size" });
  else {
    await page.setViewportSize({ width: w.width - 40, height: w.height });
    await page.waitForTimeout(250);
    let after = await row();
    record(`focus elsewhere, resized ${w.width} to ${w.width - 40}`, before, after, !after.inBar && Math.abs(after.scrollLeft - before.scrollLeft) <= 1);
    await page.setViewportSize({ width: w.width, height: w.height });
    await setRow(17);
    const again = await row();
    await withStyle(page, REFLOWS[0].css);
    await page.waitForTimeout(250);
    after = await row();
    record("focus elsewhere, wider letters", again, after, !after.inBar && Math.abs(after.scrollLeft - again.scrollLeft) <= 1);
    await dropStyle(page);
  }

  // A link has focus and the row is swiped by hand: with no size change, it stays where it was put.
  await reachLink(page, n - 1);
  await settled(page);
  state = await row();
  if (state.max < 1) on.obs.push({ sequence: "elsewhere", phase: "swiped", notApplicable: "the row does not overflow at this size" });
  else {
    await setRow(0);
    const held = await row();
    await page.waitForTimeout(250);
    const after = await row();
    record("focus on the last link, row swiped back", held, after, Math.abs(after.scrollLeft - held.scrollLeft) <= 1);
  }
}

async function main() {
  if (!fs.existsSync(path.join(SITE, "findings", "fvtge-reporting", "index.html"))) {
    console.error(`No built finding under ${SITE}: run python -m tests.build_sectnav_fixture or ./preview-build.sh first.`);
    process.exit(2);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const { server, port } = await serve(SITE);
  const base = `http://127.0.0.1:${port}`;
  const results = [];
  try {
    for (const b of pick(BROWSERS, "browser")) {
      const browser = await b.type().launch(b.opts);
      try {
        for (const p of pick(PAGES, "page")) for (const w of pick(WIDTHS, "width")) for (const mode of pick(MODES, "mode")) {
          const ctx = `${p.label} ${b.label} @${w.label} ${mode.label}`;
          const context = await browser.newContext({ viewport: { width: w.width, height: w.height },
            javaScriptEnabled: mode.js, reducedMotion: mode.reducedMotion || "no-preference" });
          const page = await context.newPage();
          const errors = [];
          page.on("pageerror", (e) => errors.push(String(e).split("\n")[0]));
          let broken = null;
          if (mode.breakScript) {
            await page.route(base + p.path, async (route) => {
              const resp = await route.fetch();
              const html = await resp.text();
              broken = html.split("</nav><script>").length - 1;
              const body = html.replace("</nav><script>", `</nav><script>throw new Error(${JSON.stringify(MADE_TO_FAIL)});`);
              await route.fulfill({ response: resp, body });
            });
          }
          const r = { ctx, page: p.label, browser: b.label, width: w.label, mode: mode.label, findings: [], obs: [] };
          const on = observer(page, ctx);
          on.ctx = ctx;
          try {
            const resp = await page.goto(base + p.path, { waitUntil: "load", timeout: 30000 });
            if (!resp || resp.status() >= 400) throw new Error(`HTTP ${resp ? resp.status() : "none"}`);
            await page.waitForTimeout(300); // fonts are local; page timers are not used, see settled()
            const st = await page.evaluate(navState);
            r.nav = st;
            if (!st.present || !st.shown) r.findings.push({ sequence: "setup", kind: "no-bar", detail: `${ctx}: the section bar is not on screen, so nothing was measured` });
            else {
              if (b.enlarged && !(st.body >= 28)) r.findings.push({ sequence: "setup", kind: "not-enlarged", detail: `${ctx}: body text is ${st.body}px, so the text was not enlarged` });
              // Which layout: the script's class whenever the script ran; the scrolling row only on
              // phones with it; the wrapped list otherwise.
              const wantClass = mode.js && !mode.breakScript;
              const wantScroll = w.phone && wantClass;
              if (st.enhanced !== wantClass || st.scrolls !== wantScroll || st.wraps === wantScroll) {
                r.findings.push({ sequence: "setup", kind: "layout-mode", detail: `${ctx}: expected the ${wantScroll ? "scrolling row" : "wrapped list"}${wantClass ? " with" : " without"} the script's class, found enhanced=${st.enhanced} scrolls=${st.scrolls} wraps=${st.wraps}` });
              }
              if (!wantScroll && st.position !== "static") r.findings.push({ sequence: "setup", kind: "fallback-pinned", detail: `${ctx}: the wrapped list is position ${st.position}; only the enhanced row may pin` });
              if (st.pageWider) r.findings.push({ sequence: "setup", kind: "page-wider", detail: `${ctx}: the page is wider than the screen` });
              for (const s of wanted) {
                on.start(s);
                if (s === "walk") r.enteredFrom = await walk(page, on, !!mode.reducedMotion);
                else if (s === "rapid") await rapid(page, on);
                else if (s === "edge") await edge(page, on, w, ctx);
                else if (s === "resize") await resize(page, on, w);
                else if (s === "reflow") await reflow(page, on);
                else if (s === "elsewhere" && wantScroll) await elsewhere(page, on, w, ctx);
                else if (s !== "elsewhere") throw new Error(`unknown sequence ${s}`);
              }
            }
          } catch (e) {
            r.findings.push({ sequence: "setup", kind: "load-failed", detail: `${ctx}: ${String(e).split("\n")[0]}` });
          }
          r.findings.push(...on.findings);
          r.obs = on.obs;
          // Only the deliberate error is excused, and only where it was deliberately caused.
          const unexpected = errors.filter((e) => !e.includes(MADE_TO_FAIL));
          if (unexpected.length) r.findings.push({ sequence: "setup", kind: "page-error", detail: `${ctx}: ${unexpected.join("; ")}` });
          if (mode.breakScript) {
            r.injectedErrors = errors.filter((e) => e.includes(MADE_TO_FAIL));
            r.scriptsBroken = broken;
            // A page with the section script must have had exactly that one broken, or the failure
            // mode was not tested. A page without one (the code before this fix) has nothing to break.
            if (broken > 1) r.findings.push({ sequence: "setup", kind: "break-failed", detail: `${ctx}: ${broken} scripts follow a nav; expected one` });
            if (broken === 1 && r.injectedErrors.length !== 1) r.findings.push({ sequence: "setup", kind: "break-failed", detail: `${ctx}: the broken section script threw ${r.injectedErrors.length} times; expected once` });
          } else if (errors.length !== unexpected.length) {
            r.findings.push({ sequence: "setup", kind: "break-failed", detail: `${ctx}: the deliberate error appeared in a mode that does not cause it` });
          }
          results.push(r);
          await context.close();
          console.log(`${r.findings.length ? "FAIL" : "ok  "}  ${ctx}  (${r.obs.length} observations)`);
          for (const f of r.findings.slice(0, 4)) console.log(`        ${f.sequence} ${f.kind}: ${f.detail}`);
          if (r.findings.length > 4) console.log(`        ... and ${r.findings.length - 4} more`);
        }
      } finally { await browser.close(); }
    }
  } finally { server.close(); }

  const failed = results.filter((r) => r.findings.length);
  const allObs = results.flatMap((r) => r.obs);
  const bySequence = Object.fromEntries(wanted.map((s) => {
    const inSeq = allObs.filter((o) => o.sequence === s);
    return [s, { observations: inSeq.filter((o) => !o.notApplicable).length, notApplicable: inSeq.filter((o) => o.notApplicable).length,
      findings: results.flatMap((r) => r.findings).filter((f) => f.sequence === s).length }];
  }));
  const summary = { site: SITE, states: results.length, observations: allObs.filter((o) => !o.notApplicable).length, failedStates: failed.length,
    findings: failed.reduce((n, r) => n + r.findings.length, 0), bySequence,
    setupFindings: results.flatMap((r) => r.findings).filter((f) => f.sequence === "setup").length,
    linkOffScreenVerticallyAfterReflow: allObs.filter((o) => o.offScreenVertically).length };
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify({ summary, results }, null, 1));
  console.log(`\n${results.length} states, ${summary.observations} observations, ${summary.findings} findings in ${failed.length} states -> ${path.join(OUT, "results.json")}`);
  for (const [s, c] of Object.entries(bySequence)) console.log(`  ${s.padEnd(10)} ${String(c.observations).padStart(5)} observations  ${String(c.findings).padStart(5)} findings${c.notApplicable ? `  (${c.notApplicable} not applicable: the row does not overflow)` : ""}`);
  if (summary.setupFindings) console.log(`  setup      ${String(summary.setupFindings).padStart(5)} findings`);
  console.log(`  a resize or reflow left the link off screen vertically (recorded, not judged): ${summary.linkOffScreenVerticallyAfterReflow}`);
  const want = pick(BROWSERS, "browser").length * pick(PAGES, "page").length * pick(WIDTHS, "width").length * pick(MODES, "mode").length;
  const unmeasured = wanted.filter((s) => !bySequence[s].observations);
  if (!want || results.length !== want || unmeasured.length) {
    const phoneWithScript = pick(WIDTHS, "width").some((w) => w.phone) && pick(MODES, "mode").some((m) => m.js && !m.breakScript);
    if (results.length !== want || unmeasured.some((s) => s !== "elsewhere" || phoneWithScript)) {
      console.error(`Nothing, or not everything, was measured (${unmeasured.join(", ") || "states missing"}): this is not a pass.`);
      process.exit(1);
    }
  }
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
