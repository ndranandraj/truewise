#!/usr/bin/env node
/* Compare the program-table variants for the JavaScript-off decision (B or C).
 *
 *   python3 tests/table_variants.py            build site/_measure/{partial,full,full-cv,list}
 *   node tests/compare_table_variants.js       measure them (needs a built site/ for CSS and JS)
 *
 * Same build, same server, same mobile conditions for every variant (perf_probe.CONDITIONS: 390px,
 * CPU 4x slower, 1.6 Mbps / 150 ms). For each variant it records:
 *   load        LCP, CLS, TBT, transfer and element count, over 5 cold runs (median and range)
 *   JS off      how many program rows a reader can reach
 *   interaction time from input to updated count for search and filter, time to next paint for a
 *               sort click, and long-task time while scrolling the whole page (3 runs each)
 * and writes table-variants-<stamp>.md with the results side by side. It judges nothing itself:
 * the release criteria are in truewise-review-noscript-programs-2026-09-27.md.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const http = require("http");
const perf = require("./perf_probe.js");

const ROOT = path.resolve(__dirname, "..");
const SITE = path.join(ROOT, "site");
const VARIANTS = ["partial", "full", "full-cv", "list"];
const MIME = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
  ".json": "application/json", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".csv": "text/csv", ".png": "image/png" };

let chromium;
try { ({ chromium } = require("playwright")); } catch (_) {
  console.error("playwright is not installed: npm install && npx playwright install chromium");
  process.exit(2);
}
for (const v of VARIANTS) {
  if (!fs.existsSync(path.join(SITE, "_measure", v, "index.html"))) {
    console.error(`site/_measure/${v}/ is missing: run python3 tests/table_variants.py first`);
    process.exit(2);
  }
}
if (!fs.existsSync(path.join(SITE, "components", "table.js"))) {
  console.error("site/components/ is missing: run python3 -m pipeline.build_components");
  process.exit(2);
}

function serve(dir) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let file = path.join(dir, decodeURIComponent(req.url.split("?")[0]));
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
      if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
      res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

async function throttledPage(browser, opts = {}) {
  const ctx = await browser.newContext({ viewport: perf.CONDITIONS.viewport, isMobile: true, hasTouch: true,
    deviceScaleFactor: 1, javaScriptEnabled: opts.js !== false });
  const page = await ctx.newPage();
  if (opts.js !== false) {
    await page.addInitScript(perf.installObservers);
    await page.addInitScript(() => {
      window.__long = 0; window.__events = [];
      try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long += e.duration; })
        .observe({ type: "longtask", buffered: true }); } catch (_) {}
      try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__events.push(e.duration); })
        .observe({ type: "event", durationThreshold: 16, buffered: true }); } catch (_) {}
    });
  }
  // Scripts blocked but JavaScript on: the page a reader gets when table.js fails to load, and the
  // closest measurable stand-in for JavaScript off (the observers need JavaScript to report).
  if (opts.blockScripts) await page.route("**/components/*.js", (r) => r.abort());
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", perf.CONDITIONS.network);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: perf.CONDITIONS.cpuThrottlingRate });
  return { ctx, page };
}

const median = (a) => { const s = a.filter((x) => x != null).sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; };
const range = (a) => { const s = a.filter((x) => x != null); return s.length ? `${Math.round(Math.min(...s))} to ${Math.round(Math.max(...s))}` : "n/a"; };

async function load(browser, url) {
  const runs = [];
  for (let i = 0; i < perf.CONDITIONS.runs; i++) {
    const { ctx, page } = await throttledPage(browser);
    await page.goto(url, { waitUntil: "load", timeout: 90000 });
    await page.waitForTimeout(2500);
    const r = await page.evaluate(perf.readPerf);
    r.elements = await page.evaluate(() => document.getElementsByTagName("*").length);
    runs.push(r);
    await ctx.close();
  }
  const pick = (k) => runs.map((r) => r[k]);
  return { lcp: median(pick("lcp")), lcpRange: range(pick("lcp")), cls: median(pick("cls")), tbt: median(pick("tbt")),
    tbtRange: range(pick("tbt")), kb: median(pick("transferKB")), elements: median(pick("elements")) };
}

async function jsOff(browser, url) {
  const { ctx, page } = await throttledPage(browser, { js: false });
  await page.goto(url, { waitUntil: "load", timeout: 90000 });
  const rows = await page.evaluate(() => document.querySelectorAll(".tw-table tbody tr").length);
  const notice = await page.evaluate(() => !!document.querySelector("[data-tw-partial]"));
  await ctx.close();
  return { rows, notice };
}

/* Time from a change to the count line showing its result, plus one frame, in the page's own clock. */
/* Time from choosing "Median earnings" in the sort control to the reordered first row being painted.
 * At phone width the header buttons are hidden and the visible control is the sort select. */
function timeSort() {
  return (async () => {
    const first = () => ((document.querySelector(".tw-table tbody tr") || {}).textContent || "");
    const before = first();
    const sel = document.querySelector('[data-tw-focus="sortsel"]');
    const btn = document.querySelector('[data-tw-focus="sort-earnings"]');
    const t0 = performance.now();
    if (sel && sel.offsetParent !== null) { sel.value = "earnings"; sel.dispatchEvent(new Event("change", { bubbles: true })); }
    else if (btn) btn.click();
    else return null;
    await new Promise((done) => {
      const stop = t0 + 30000;
      const tick = () => (first() !== before || performance.now() > stop ? done() : requestAnimationFrame(tick));
      tick();
    });
    await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
    return first() === before ? null : performance.now() - t0;
  })();
}

/* Playwright passes one argument to a page function, so the three values travel as one object. */
function timeUntilCount({ sel, value, kind }) {
  return (async () => {
    const count = () => (document.querySelector(".tw-table__count") || {}).textContent || "";
    const before = count();
    const el = document.querySelector(sel);
    if (!el) return null;
    const t0 = performance.now();
    el.value = value;
    el.dispatchEvent(new Event(kind, { bubbles: true }));
    await new Promise((done) => {
      const stop = t0 + 30000;
      const tick = () => (count() !== before || performance.now() > stop ? done() : requestAnimationFrame(tick));
      tick();
    });
    await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));
    return performance.now() - t0;
  })();
}

/* The static page on its own: every row the HTML carries, rendered and scrolled with no enhancement. */
async function staticRun(browser, url) {
  const runs = [];
  for (let i = 0; i < 3; i++) {
    const { ctx, page } = await throttledPage(browser, { blockScripts: true });
    await page.goto(url, { waitUntil: "load", timeout: 90000 });
    await page.waitForTimeout(2500);
    const p = await page.evaluate(perf.readPerf);
    const rows = await page.evaluate(() => document.querySelectorAll(".tw-table tbody tr").length);
    const elements = await page.evaluate(() => document.getElementsByTagName("*").length);
    await page.evaluate(() => { window.__long = 0; });
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    for (let y = 0; y < height; y += 700) { await page.mouse.wheel(0, 700); await page.waitForTimeout(60); }
    await page.waitForTimeout(500);
    runs.push({ lcp: p.lcp, tbt: p.tbt, cls: p.cls, rows, elements, height, scroll: await page.evaluate(() => window.__long) });
    await ctx.close();
  }
  const m = (k) => median(runs.map((r) => r[k]));
  return { lcp: m("lcp"), tbt: m("tbt"), cls: m("cls"), rows: m("rows"), elements: m("elements"), height: m("height"), scroll: m("scroll") };
}

async function interactions(browser, url) {
  const out = { search: [], filter: [], sort: [], scrollLong: [] };
  for (let i = 0; i < 3; i++) {
    const { ctx, page } = await throttledPage(browser);
    await page.goto(url, { waitUntil: "load", timeout: 90000 });
    await page.waitForTimeout(1500);
    const hasTable = await page.evaluate(() => !!document.querySelector('[data-tw-focus="q"]'));
    if (hasTable) {
      out.search.push(await page.evaluate(timeUntilCount, { sel: '[data-tw-focus="q"]', value: "engineering", kind: "input" }));
      out.filter.push(await page.evaluate(timeUntilCount, { sel: '[data-tw-focus="verdict"]', value: "fail", kind: "change" }));
      // Back to the whole list, then sort it: sorting the one-row "fail" view would change nothing
      // and measure nothing (the first run reported n/a for every variant for that reason).
      await page.evaluate(timeUntilCount, { sel: '[data-tw-focus="verdict"]', value: "", kind: "change" });
      await page.evaluate(timeUntilCount, { sel: '[data-tw-focus="q"]', value: "", kind: "input" });
      out.sort.push(await page.evaluate(timeSort));
    }
    await page.evaluate(() => { window.__long = 0; });
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    for (let y = 0; y < height; y += 700) { await page.mouse.wheel(0, 700); await page.waitForTimeout(60); }
    await page.waitForTimeout(500);
    out.scrollLong.push(await page.evaluate(() => window.__long));
    out.height = height;
    await ctx.close();
  }
  return { search: median(out.search), filter: median(out.filter), sort: median(out.sort),
    scrollLong: median(out.scrollLong), height: out.height };
}

(async () => {
  const { server, port } = await serve(SITE);
  const browser = await chromium.launch();
  const results = {};
  try {
    for (const v of VARIANTS) {
      const url = `http://127.0.0.1:${port}/_measure/${v}/`;
      console.log(`${v}: load`); const l = await load(browser, url);
      console.log(`${v}: JavaScript off`); const off = await jsOff(browser, url);
      console.log(`${v}: interactions`); const ix = await interactions(browser, url);
      console.log(`${v}: scripts blocked`); const st = await staticRun(browser, url);
      const zlib = require("zlib");
      const dir = path.join(SITE, "_measure", v);
      const gz = (f) => (fs.existsSync(f) ? Math.round(zlib.gzipSync(fs.readFileSync(f), { level: 9 }).length / 1024) : 0);
      // The local server does not compress; production does. Transfer above is uncompressed.
      results[v] = { ...l, off, ...ix, st, gz: gz(path.join(dir, "index.html")), tailGz: gz(path.join(dir, "programs-tail.json")) };
    }
  } finally {
    await browser.close(); server.close();
  }
  const r = (x) => (x == null ? "n/a" : Math.round(x));
  const L = [`# Program-table variants, ${new Date().toISOString().slice(0, 16)}`, "",
    `Penn State (489 programs). 390px, CPU ${perf.CONDITIONS.cpuThrottlingRate}x, 1.6 Mbps / 150 ms. Load: median of ${perf.CONDITIONS.runs} cold runs. Interactions: median of 3.`, "",
    "| | partial (today, A) | full (B) | full-cv (B) | list (C) |", "|---|---|---|---|---|"];
  const row = (label, f) => L.push(`| ${label} | ${VARIANTS.map((v) => f(results[v])).join(" | ")} |`);
  row("LCP ms (range)", (x) => `${r(x.lcp)} (${x.lcpRange})`);
  row("CLS", (x) => (x.cls == null ? "n/a" : x.cls.toFixed(3)));
  row("TBT ms (range)", (x) => `${r(x.tbt)} (${x.tbtRange})`);
  row("Transfer KB (uncompressed, local)", (x) => r(x.kb));
  row("Elements after load (JS on)", (x) => r(x.elements));
  row("Rows reachable, JS off", (x) => `${x.off.rows}${x.off.notice ? " (notice shown)" : ""}`);
  row("Search to count, ms", (x) => r(x.search));
  row("Filter to count, ms", (x) => r(x.filter));
  row("Sort to reordered rows, ms", (x) => r(x.sort));
  row("HTML gzip KB (tail on use)", (x) => `${x.gz}${x.tailGz ? " (+" + x.tailGz + ")" : ""}`);
  row("Long tasks while scrolling, ms", (x) => r(x.scrollLong));
  row("Page height px", (x) => r(x.height));
  L.push("| **Scripts blocked (static HTML only)** | | | | |");
  row("Rows rendered", (x) => r(x.st.rows));
  row("Elements", (x) => r(x.st.elements));
  row("LCP ms", (x) => r(x.st.lcp));
  row("TBT ms", (x) => r(x.st.tbt));
  row("CLS", (x) => (x.st.cls == null ? "n/a" : x.st.cls.toFixed(3)));
  row("Long tasks while scrolling, ms", (x) => r(x.st.scroll));
  row("Page height px", (x) => r(x.st.height));
  L.push("", `CLS targets: ${perf.CLS_GOOD} good, ${perf.CLS_POOR} poor. "n/a" for interactions on the list page means it has no search, filter or sort.`);
  const out = path.join(ROOT, `table-variants-${Date.now()}.md`);
  fs.writeFileSync(out, L.join("\n") + "\n");
  fs.writeFileSync(out.replace(/\.md$/, ".json"), JSON.stringify(results, null, 2));
  console.log(L.join("\n"));
  console.log(`\nwrote ${out}`);
})().catch((e) => { console.error(e); process.exit(1); });
