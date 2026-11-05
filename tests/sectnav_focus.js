#!/usr/bin/env node
/* The section links, by keyboard (October 2026).
 *
 *   node tests/sectnav_focus.js              against the built site/
 *   node tests/sectnav_focus.js --site DIR   against another built tree
 *   node tests/sectnav_focus.js --out DIR    results directory (default sectnav-focus-<stamp>/)
 *   --only browser=firefox-200,width=320,mode=js,page=profile-ucla   a subset, for working on it
 *
 * On phones the finding's and every profile's section links ran sideways under a 36px fade, and a
 * link reached with Tab or Shift+Tab stayed partly under the fade or past the left edge: browsers
 * scroll a focused element only just into view and ignore scroll-padding when moving focus (review
 * of 11 October: 3 of the finding's 7 links at each phone width, and UCLA's Sources link at 200%
 * text). The fix has two halves, and this checks both:
 *   - with the script, the row scrolls and each focused link, focus ring included, is moved clear of
 *     the fade and the edges;
 *   - without it (JavaScript off, or the script failing), the links wrap and nothing is hidden.
 *
 * Every link is reached by real Tab and Shift+Tab, forwards and back, in Chromium and Firefox, at
 * normal text and at Firefox's native 200% text, with reduced motion, with JavaScript off and with
 * the script made to fail. What is measured is the focus ring (the outline, from the computed
 * outline width and offset), not only the link's box: a ring cut off at the scroller's edge or under
 * the fade was the remaining polish item.
 *
 * Like the layout check, it does not report a pass it has not earned: a page that does not load, a
 * bar that is missing, text that was not enlarged, or a run with no observations is a failure.
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
  const ow = cs.outlineStyle === "none" ? 0 : parseFloat(cs.outlineWidth) || 0;
  const reach = ow ? ow + (parseFloat(cs.outlineOffset) || 0) : 0;
  const r = a.getBoundingClientRect();
  const box = { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
  const ring = { left: r.left - reach, right: r.right + reach, top: r.top - reach, bottom: r.bottom + reach };
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
  return { index, count: links.length, text: a.textContent.trim(), reach, box, ring, clips, fade, header,
    navInHeader: !!(hdr && hdr.contains(nav)), scrollLeft: ul ? ul.scrollLeft : null, scrollY: window.scrollY };
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

/** Wait until the focused link, the row's scroll and the page's scroll stop moving (smooth scrolling,
 *  if any, settles), up to 1.5s. Reading too early once called a moving page clean. The waiting is
 *  done here, not in the page: with JavaScript off the page's own timers never fire. */
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
function judge(m, ctx, phase) {
  const out = [];
  const at = `${ctx} ${phase} link ${m.index + 1}/${m.count} "${m.text}"`;
  for (const what of ["box", "ring"]) {
    const g = m[what];
    for (const c of m.clips) {
      const cut = [g.left < c.left - EPS && "left", g.right > c.right + EPS && "right",
        g.top < c.top - EPS && "top", g.bottom > c.bottom + EPS && "bottom"].filter(Boolean);
      if (cut.length) out.push({ kind: `${what}-clipped`, detail: `${at}: ${what === "ring" ? "focus ring" : "link"} cut at the ${cut.join(" and ")} of ${c.tag} (${what} ${fmt(g)}, visible ${fmt(c)})` });
    }
    if (m.fade && g.right > m.fade.left + EPS && g.left < m.fade.right && g.bottom > m.fade.top && g.top < m.fade.bottom) {
      out.push({ kind: `${what}-under-fade`, detail: `${at}: ${what === "ring" ? "focus ring" : "link"} reaches ${(g.right - m.fade.left).toFixed(1)}px into the fade (fade from ${m.fade.left.toFixed(1)}px)` });
    }
    if (m.header != null && !m.navInHeader && g.top < m.header - EPS) {
      out.push({ kind: `${what}-under-header`, detail: `${at}: ${what === "ring" ? "focus ring" : "link"} top ${g.top.toFixed(1)}px is under the pinned header (to ${m.header.toFixed(1)}px)` });
    }
  }
  if (!m.reach) out.push({ kind: "no-focus-ring", detail: `${at}: the focused link shows no outline` });
  return out;
}
const fmt = (b) => `${b.left.toFixed(1)}..${b.right.toFixed(1)} x ${b.top.toFixed(1)}..${b.bottom.toFixed(1)}`;

async function walk(page, ctx, reduced) {
  const findings = [], obs = [];
  const n = await page.evaluate(() => document.querySelectorAll(".sectnav a").length);
  const expect = async (want, phase) => {
    await page.waitForTimeout(50);
    const early = await page.evaluate(measure);
    const waited = await settled(page);
    const m = await page.evaluate(measure);
    if (m.index !== want) {
      obs.push({ phase, want, waitedMs: Math.round(waited), ...m });
      findings.push({ kind: "wrong-focus", detail: `${ctx} ${phase}: expected link ${want + 1} focused, found ${m.index < 0 ? m.tag : "link " + (m.index + 1)}` });
      return;
    }
    // A page that smooth-scrolls to the focused link can look still before it starts moving. Any
    // finding is measured again 1.3s later, and only what remains is reported; both are recorded.
    let got = judge(m, ctx, phase), final = m, first = null;
    if (got.length) {
      await page.waitForTimeout(1300);
      final = await page.evaluate(measure);
      first = { findings: got.map((f) => f.kind), box: m.box, scrollY: m.scrollY };
      got = final.index === want ? judge(final, ctx, phase) : [{ kind: "wrong-focus", detail: `${ctx} ${phase}: focus moved on its own` }];
    }
    obs.push({ phase, want, waitedMs: Math.round(waited), ...final, firstReading: first });
    findings.push(...got);
    // With reduced motion nothing may animate into place: the first frame after focus is the result.
    if (reduced && early.index === want) findings.push(...judge(early, ctx, phase + " (first frame)"));
  };
  // Enter the row by keyboard: from the element before the first link, Tab. Firefox makes the
  // scrolling list itself a Tab stop (native behaviour, kept), so that element may be the list.
  await page.evaluate(() => document.querySelector(".sectnav a").focus());
  await page.keyboard.press("Shift+Tab");
  const before = await page.evaluate(() => {
    const a = document.activeElement;
    return !a.closest(".sectnav a") ? (a.matches(".sectnav ul") ? "the list" : a.tagName) : null;
  });
  if (!before) findings.push({ kind: "walk-setup", detail: `${ctx}: Shift+Tab from the first link stayed on a link` });
  await page.keyboard.press("Tab");
  await expect(0, "forward");
  for (let i = 1; i < n; i++) { await page.keyboard.press("Tab"); await expect(i, "forward"); }
  // Leave past the last link, let the page finish scrolling to what comes next, then come back with
  // Shift+Tab and walk to the first. (Without the pause, Chromium's smooth scroll to the next element
  // can swallow the scroll back: a page-wide behaviour of html { scroll-behavior: smooth }, recorded
  // separately, not something the section bar can fix.)
  await page.keyboard.press("Tab");
  await page.waitForTimeout(1500);
  await page.keyboard.press("Shift+Tab");
  await expect(n - 1, "reverse");
  for (let i = n - 2; i >= 0; i--) { await page.keyboard.press("Shift+Tab"); await expect(i, "reverse"); }
  return { findings, obs, links: n, enteredFrom: before };
}

async function main() {
  if (!fs.existsSync(path.join(SITE, "findings", "fvtge-reporting", "index.html"))) {
    console.error(`No built finding under ${SITE}: run ./preview-build.sh first.`);
    process.exit(2);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const { server, port } = await serve(SITE);
  const base = `http://127.0.0.1:${port}`;
  const results = [];
  let observations = 0;
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
              const body = html.replace("</nav><script>", '</nav><script>throw new Error("sectnav_focus: the section script was made to fail");');
              await route.fulfill({ response: resp, body });
            });
          }
          const r = { ctx, page: p.label, browser: b.label, width: w.label, mode: mode.label, findings: [], obs: [] };
          try {
            const resp = await page.goto(base + p.path, { waitUntil: "load", timeout: 30000 });
            if (!resp || resp.status() >= 400) throw new Error(`HTTP ${resp ? resp.status() : "none"}`);
            await page.waitForTimeout(300); // fonts are local; page timers are not used, see settled()
            const st = await page.evaluate(navState);
            r.nav = st;
            if (!st.present || !st.shown) r.findings.push({ kind: "no-bar", detail: `${ctx}: the section bar is not on screen, so nothing was measured` });
            else {
              if (b.enlarged && !(st.body >= 28)) r.findings.push({ kind: "not-enlarged", detail: `${ctx}: body text is ${st.body}px, so the text was not enlarged` });
              // Which layout: the script's class whenever the script ran; the scrolling row only on
              // phones with it; the wrapped list otherwise.
              const wantClass = mode.js && !mode.breakScript;
              const wantScroll = w.phone && wantClass;
              if (st.enhanced !== wantClass || st.scrolls !== wantScroll || st.wraps === wantScroll) {
                r.findings.push({ kind: "layout-mode", detail: `${ctx}: expected the ${wantScroll ? "scrolling row" : "wrapped list"}${wantClass ? " with" : " without"} the script's class, found enhanced=${st.enhanced} scrolls=${st.scrolls} wraps=${st.wraps}` });
              }
              if (!wantScroll && st.position !== "static") r.findings.push({ kind: "fallback-pinned", detail: `${ctx}: the wrapped list is position ${st.position}; only the enhanced row may pin` });
              if (st.pageWider) r.findings.push({ kind: "page-wider", detail: `${ctx}: the page is wider than the screen` });
              const wk = await walk(page, ctx, !!mode.reducedMotion);
              r.findings.push(...wk.findings);
              r.obs = wk.obs;
              r.enteredFrom = wk.enteredFrom;
              observations += wk.obs.length;
            }
          } catch (e) {
            r.findings.push({ kind: "load-failed", detail: `${ctx}: ${String(e).split("\n")[0]}` });
          }
          if (errors.length && !mode.breakScript) r.findings.push({ kind: "page-error", detail: `${ctx}: ${errors.join("; ")}` });
          if (mode.breakScript) {
            r.injectedErrors = errors;
            r.scriptsBroken = broken;
            // A page with the section script must have had exactly that one broken, or the failure
            // mode was not tested. A page without one (the code before this fix) has nothing to break.
            if (broken > 1) r.findings.push({ kind: "break-failed", detail: `${ctx}: ${broken} scripts follow a nav; expected one` });
            if (broken === 1 && !errors.some((e) => e.includes("made to fail"))) r.findings.push({ kind: "break-failed", detail: `${ctx}: the broken section script did not throw` });
          }
          results.push(r);
          await context.close();
          console.log(`${r.findings.length ? "FAIL" : "ok  "}  ${ctx}  (${r.obs.length} focus observations)`);
          for (const f of r.findings.slice(0, 4)) console.log(`        ${f.kind}: ${f.detail}`);
          if (r.findings.length > 4) console.log(`        ... and ${r.findings.length - 4} more`);
        }
      } finally { await browser.close(); }
    }
  } finally { server.close(); }

  const failed = results.filter((r) => r.findings.length);
  const summary = { site: SITE, states: results.length, observations, failedStates: failed.length,
    findings: failed.reduce((n, r) => n + r.findings.length, 0) };
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify({ summary, results }, null, 1));
  console.log(`\n${results.length} states, ${observations} focus observations, ${summary.findings} findings in ${failed.length} states -> ${path.join(OUT, "results.json")}`);
  const want = pick(BROWSERS, "browser").length * pick(PAGES, "page").length * pick(WIDTHS, "width").length * pick(MODES, "mode").length;
  if (!observations || !want || results.length !== want) {
    console.error("Nothing, or not everything, was measured: this is not a pass.");
    process.exit(1);
  }
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
