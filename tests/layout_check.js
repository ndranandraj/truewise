#!/usr/bin/env node
/* The layout and interaction check: decision B.
 *
 *   node tests/layout_check.js              against the built site/ directory
 *   node tests/layout_check.js --live       against https://truewise.dev
 *   node tests/layout_check.js --url X      against any base URL, for a preview deploy
 *   node tests/layout_check.js --open       leave the browser visible
 *   node tests/layout_check.js --perf       also time each route (5 cold runs, adds minutes)
 *   node tests/layout_check.js --perf --record-baseline   write tests/perf_baseline.json
 *
 * Six routes at four widths, plus the interactions the static probe cannot trigger itself. Writes
 * screenshots, a JSON result and a markdown report to layout-check-<stamp>/, and exits non-zero on
 * a blocking finding.
 *
 * WHY IT EXISTS. Three rounds of browser review on work whose tests were green found seven defects.
 * The suite could not have found any of them: jsdom has no layout engine, so every rectangle it
 * reports is zero, and two of my own assertions passed while agreeing with a bug. Everything about
 * geometry, overflow and post-interaction focus was simply outside what the tests could observe.
 *
 * WHAT IT REFUSES TO DO. It will not report a pass it has not earned. If the browser is missing, if
 * the server does not come up, or if it completes zero page-states, it exits non-zero and says so.
 * A check that returns green over nothing is the exact defect this release spent three weeks on:
 * the old monitor looked healthy for two months while accumulating nothing, and the reachability
 * probe drew a conclusion about a server it had never reached. A harness that cannot fail for the
 * right reason is decoration.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const http = require("http");

const { probe, focusState, WIDTHS, ROUTES } = require("./layout_probe.js");
const perf = require("./perf_probe.js");

const BASELINE = path.resolve(__dirname, "perf_baseline.json");

const ROOT = path.resolve(__dirname, "..");
const SITE = path.join(ROOT, "site");

const args = process.argv.slice(2);
const flag = (n) => args.includes(n);
const valueOf = (n) => { const i = args.indexOf(n); return i === -1 ? null : args[i + 1]; };

/* ---------------------------------------------------------------------------------------------
 * Preconditions, each with its own message. "Something went wrong" costs more time than it saves.
 * ------------------------------------------------------------------------------------------- */

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch (_) {
  console.error(
    "playwright is not installed.\n\n" +
    "  npm install                      (installs from package.json)\n" +
    "  npx playwright install chromium  (downloads the browser, about 170 MB)\n",
  );
  process.exit(2);
}

const MIME = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".png": "image/png", ".svg": "image/svg+xml", ".xml": "application/xml",
  ".woff2": "font/woff2", ".csv": "text/csv; charset=utf-8", ".txt": "text/plain; charset=utf-8",
};

/** Serve site/ the way Cloudflare does: a directory maps to its index.html. Without that, every
 *  route in ROUTES 404s and the run reports a clean sweep over six error pages. */
function serve(dir) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let p = decodeURIComponent(req.url.split("?")[0]);
      let file = path.join(dir, p);
      try {
        if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
        if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
        res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
        fs.createReadStream(file).pipe(res);
      } catch (e) {
        res.writeHead(500); res.end(String(e));
      }
    });
    server.listen(0, "127.0.0.1", () => resolve({ server, port: server.address().port }));
  });
}

/* ---------------------------------------------------------------------------------------------
 * The interactions. The probe measures; this drives.
 * ------------------------------------------------------------------------------------------- */

const tableState = () => {
  const el = document.querySelector(".tw-table__count");
  const tb = document.querySelector(".tw-table tbody");
  const st = document.querySelector(".tw-table__status");
  return {
    count: el ? el.textContent.trim().replace(/\s+/g, " ") : null,
    rows: tb ? tb.querySelectorAll("tr").length : null,
    status: st ? st.textContent.trim().replace(/\s+/g, " ") : "",
    hasReveal: !!document.querySelector(".tw-more, .tw-showall"),
  };
};

/* The Careers page is NOT a tw-table. It has its own cr-* markup, its own live region (#cr-live) and
 * its own Show-more, and it carries the same three obligations: the count must match the rows, the
 * change must be announced, and focus must land on content rather than <body>. The first real run
 * reported "no program table on this route" and skipped all of it, which read as clean. */
const careersState = () => {
  const c = document.getElementById("count");
  const live = document.getElementById("cr-live");
  const tb = document.querySelector("#list .cr-table tbody");
  return {
    count: c ? c.textContent.trim().replace(/\s+/g, " ") : null,
    rows: tb ? tb.querySelectorAll("tr").length : null,
    status: live ? live.textContent.trim().replace(/\s+/g, " ") : "",
    hasMore: !!document.getElementById("cr-more"),
  };
};

async function careersInteractions(page) {
  const findings = [];
  const steps = [];
  const before = await page.evaluate(careersState);
  if (before.rows == null) {
    return { findings: [{ kind: "careers-missing", blocking: true, detail:
      "Careers rendered no #list table, so its interactions could not be driven and nothing about " +
      "them was established." }], steps };
  }

  if (before.hasMore) {
    await page.evaluate(() => document.getElementById("cr-more").click());
    await page.waitForTimeout(900);
    const after = await page.evaluate(careersState);
    const focus = await page.evaluate(focusState);
    steps.push({ step: "show-more", before, after, focus });
    if (focus.onBody) {
      findings.push({ kind: "careers-focus", blocking: true, detail:
        "Show more on Careers left focus on <body> rather than the first revealed row." });
    }
    if (!after.status) {
      findings.push({ kind: "careers-silent", blocking: true, detail:
        "Show more on Careers changed the list and #cr-live stayed empty." });
    }
    const claimed = (after.count.match(/^Showing ([\d,]+) of/) || [])[1];
    if (claimed && +claimed.replace(/,/g, "") !== after.rows) {
      findings.push({ kind: "careers-count", blocking: true, detail:
        `Careers says "${after.count}" but rendered ${after.rows} rows.` });
    }
  }

  /* The announcement is checked against what the region said BEFORE the search, not merely against
   * emptiness. An empty region is silent; a region still holding the previous sentence is worse,
   * because it is a confident false statement. Careers shipped exactly that: reveal 50 rows, then
   * search, and the region kept reading "25 more shown. Showing 50 of 738" over a list of 13. */
  const preSearchStatus = (await page.evaluate(careersState)).status;
  await page.evaluate(() => {
    const q = document.getElementById("q");
    q.focus(); q.value = "nursing"; q.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForTimeout(900);
  const after = await page.evaluate(careersState);
  steps.push({ step: "search", typed: "nursing", preSearchStatus, after });

  const claimed = (after.count.match(/^(?:Showing )?([\d,]+)/) || [])[1];
  if (claimed && after.rows != null && +claimed.replace(/,/g, "") < after.rows) {
    findings.push({ kind: "careers-search-count", blocking: true, detail:
      `Careers search says "${after.count}" while rendering ${after.rows} rows.` });
  }
  if (!after.status) {
    findings.push({ kind: "careers-search-silent", blocking: true, detail:
      `Searching Careers changed the list to "${after.count}" and the live region is empty.` });
  } else if (after.status === preSearchStatus && preSearchStatus) {
    findings.push({ kind: "careers-search-stale", blocking: true, detail:
      `Searching Careers changed the list to "${after.count}" but the live region still reads ` +
      `"${after.status}", which is now false.` });
  }
  return { findings, steps };
}

/* Compare carries schools in its URL, so the only thing to establish here is that they actually
 * arrived. If they did not, every "clean" at every width described an empty page. */
async function compareInteractions(page) {
  const state = await page.evaluate(() => ({
    schools: document.querySelectorAll("table thead th").length,
    hasTable: !!document.querySelector("table"),
    rows: document.querySelectorAll("table tbody tr").length,
  }));
  if (!state.hasTable || state.rows === 0) {
    return { findings: [{ kind: "compare-empty", blocking: true, detail:
      "Compare rendered no comparison table, so the stacked-card layout this route exists to " +
      "exercise was never on screen and the width results describe an empty page." }], steps: [] };
  }
  return { findings: [], steps: [{ step: "load-with-schools", ...state }] };
}

/* ---------------------------------------------------------------------------------------------
 * Timing. Several cold runs per route, median reported with its spread.
 *
 * Each run gets a FRESH context so the HTTP cache, the connection pool and the font cache all start
 * empty. Reusing one context makes run 2 onward measure a warm cache, the median then describes a
 * repeat visitor, and the number quietly stops answering the question it was asked.
 * ------------------------------------------------------------------------------------------- */

async function measureRoute(browser, base, route, log) {
  const runs = [];
  for (let i = 0; i < perf.CONDITIONS.runs; i++) {
    const ctx = await browser.newContext({
      viewport: perf.CONDITIONS.viewport,
      isMobile: true,
      hasTouch: true,
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    await page.addInitScript(perf.installObservers);

    /* Throttling is applied through CDP, which is Chromium-only. If it is unavailable the run must
     * say the numbers are unthrottled rather than present them as if the conditions held. */
    let throttled = false;
    try {
      const cdp = await ctx.newCDPSession(page);
      await cdp.send("Network.enable");
      await cdp.send("Network.emulateNetworkConditions", perf.CONDITIONS.network);
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: perf.CONDITIONS.cpuThrottlingRate });
      throttled = true;
    } catch (e) {
      log(`    throttling unavailable: ${String(e).split("\n")[0]}`);
    }

    try {
      await page.goto(base + route.path, { waitUntil: "load", timeout: 60000 });
      /* LCP is only final once the page stops producing candidates. Settle, then read. */
      await page.waitForTimeout(2500);
      const r = await page.evaluate(perf.readPerf);
      runs.push({ ...r, throttled });
    } catch (e) {
      runs.push({ error: String(e).split("\n")[0], throttled });
    }
    await ctx.close();
  }

  const ok = runs.filter((r) => !r.error);
  const summary = {
    runs: runs.length,
    completed: ok.length,
    throttled: ok.every((r) => r.throttled),
    worstShifts: ok.flatMap((r) => r.shifts || []).sort((a, b) => b.value - a.value).slice(0, 4),
    lcp: perf.summarise(ok.map((r) => r.lcp)),
    cls: perf.summarise(ok.map((r) => r.cls)),
    tbt: perf.summarise(ok.map((r) => r.tbt)),
    fcp: perf.summarise(ok.map((r) => r.fcp)),
    transferKB: perf.summarise(ok.map((r) => r.transferKB)),
    raw: runs,
  };
  return summary;
}

async function interactions(page, route) {
  if (route.kind === "careers") return careersInteractions(page);
  if (route.kind === "compare") return compareInteractions(page);
  if (route.kind === "static") return { skipped: "static route, no interactive table", findings: [], steps: [] };

  const out = [];
  const findings = [];
  const before = await page.evaluate(tableState);
  if (before.rows == null) {
    return { findings: [{ kind: "table-missing", blocking: true, detail:
      `${route.label} is declared a program-table route and rendered no .tw-table, so none of its ` +
      `interactions were driven.` }], steps: out };
  }

  /* 1. REVEAL. Three things must agree afterwards: the rows rendered, the count line, and what was
   *    announced. "Show all 489 programs" once rendered 160 while announcing 489, and the loudest
   *    of the three statements was the false one. */
  if (before.hasReveal) {
    const label = await page.evaluate(() => {
      const b = document.querySelector(".tw-showall") || document.querySelector(".tw-more");
      b.focus(); const t = b.textContent.trim(); b.click(); return t;
    });
    await page.waitForTimeout(2500);
    const after = await page.evaluate(tableState);
    const focus = await page.evaluate(focusState);
    out.push({ step: "reveal", label, before, after, focus });

    const claimed = (after.count.match(/[\d,]+/g) || []).map((n) => +n.replace(/,/g, ""));
    if (/^Showing /.test(after.count) && claimed[0] !== after.rows) {
      findings.push({ kind: "reveal-count", blocking: true, detail:
        `After "${label}" the table says "${after.count}" but rendered ${after.rows} rows.` });
    }
    if (focus.onBody) {
      findings.push({ kind: "reveal-focus", blocking: true, detail:
        `After "${label}" focus fell to <body>, so a keyboard reader is returned to the top of the ` +
        `document instead of to the rows that just appeared.` });
    }
    if (!after.status) {
      findings.push({ kind: "reveal-silent", blocking: true, detail:
        `After "${label}" the live region is empty, so the change was drawn and never announced.` });
    }
  }

  /* 2. SORT. The sort buttons carry no id, so focus restoration is keyed on data-tw-focus. A sort
   *    that drops focus to <body> is invisible to a screenshot and obvious to a keyboard user. */
  const hasSort = await page.evaluate(() => !!document.querySelector("button.tw-th__sort"));
  if (hasSort) {
    const label = await page.evaluate(() => {
      const b = document.querySelector("button.tw-th__sort");
      b.focus(); const t = b.textContent.trim(); b.click(); return t;
    });
    await page.waitForTimeout(700);
    const focus = await page.evaluate(focusState);
    const aria = await page.evaluate(() =>
      [...document.querySelectorAll("th[aria-sort]")].map((t) => t.getAttribute("aria-sort")));
    out.push({ step: "sort", label, focus, ariaSort: aria });

    if (focus.onBody) {
      findings.push({ kind: "sort-focus", blocking: true, detail:
        `Sorting by "${label}" dropped focus to <body>.` });
    }
    if (!aria.some((v) => v === "ascending" || v === "descending")) {
      findings.push({ kind: "sort-aria", blocking: true, detail:
        `Sorting by "${label}" left every th aria-sort at "none", so the sorted column is not ` +
        `announced.` });
    }
  }

  /* 3. SEARCH. The caret check is the one that matters. The focus hint used to be taken when the
   *    tail fetch STARTED rather than immediately before the render, so a reader who typed
   *    "History" got the caret restored to position 0 and the next keystroke produced "xHistory". */
  const hasSearch = await page.evaluate(() => !!document.querySelector('[data-tw-focus="q"]'));
  if (hasSearch) {
    await page.evaluate(() => {
      const q = document.querySelector('[data-tw-focus="q"]');
      q.focus(); q.value = "nursing"; q.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await page.waitForTimeout(2500);
    const after = await page.evaluate(tableState);
    const focus = await page.evaluate(focusState);
    out.push({ step: "search", typed: "nursing", after, focus });

    if (focus.key !== "q") {
      findings.push({ kind: "search-focus", blocking: true, detail:
        `After typing, focus is on ${focus.selector} rather than the search field.` });
    } else if (focus.caret !== "nursing".length) {
      findings.push({ kind: "search-caret", blocking: true, detail:
        `The caret was restored to ${focus.caret} instead of ${"nursing".length}, so the next ` +
        `keystroke would land in the middle of what the reader typed.` });
    }
    if (!after.status) {
      findings.push({ kind: "search-silent", blocking: true, detail:
        `The result count changed to "${after.count}" and the live region is empty. The filters ` +
        `announce and search does not, which is how the failed-load disclosure was erased.` });
    }
    const m = (after.count.match(/^([\d,]+) of/) || [])[1];
    if (m && +m.replace(/,/g, "") !== after.rows) {
      findings.push({ kind: "search-count", blocking: true, detail:
        `Search says "${after.count}" but rendered ${after.rows} rows.` });
    }
  }

  return { findings, steps: out };
}

/* ------------------------------------------------------------------------------------------- */

function markdown(result) {
  const L = [];
  L.push(`# Layout and interaction check, ${result.startedAt}`);
  L.push("");
  L.push(`Base: \`${result.base}\`. ${result.states} page-states across ` +
         `${result.routes.length} routes and ${WIDTHS.length} widths.`);
  L.push("");
  L.push(result.blocking === 0
    ? `**No blocking findings.** ${result.advisory} advisory.`
    : `**${result.blocking} blocking findings.** ${result.advisory} advisory.`);
  L.push("");
  L.push("| Route | " + WIDTHS.map((w) => w.label).join(" | ") + " | Interactions |");
  L.push("|---" .repeat(WIDTHS.length + 2) + "|");
  for (const r of result.routes) {
    const cells = WIDTHS.map((w) => {
      const s = r.widths[w.label];
      if (!s) return "not run";
      const b = s.findings.filter((f) => f.blocking).length;
      const a = s.findings.length - b;
      return b ? `**${b} blocking**` : a ? `${a} advisory` : "clean";
    });
    const ix = r.interactions;
    /* "not applicable" rather than a blank or the word clean. A route whose interactions were never
     * driven has established nothing about them, and the table should not let that read as a pass. */
    const icell = ix.skipped ? `n/a, ${ix.skipped}`
      : ix.findings.length ? `**${ix.findings.length} blocking**`
      : ix.steps.length ? `${ix.steps.map((s) => s.step).join(", ")}: clean`
      : "**none driven**";
    L.push(`| ${r.label} | ${cells.join(" | ")} | ${icell} |`);
  }
  L.push("");

  const all = [];
  for (const r of result.routes) {
    for (const w of WIDTHS) {
      const s = r.widths[w.label];
      if (s) for (const f of s.findings) all.push({ where: `${r.label} @ ${w.label}`, ...f });
    }
    for (const f of r.interactions.findings) all.push({ where: `${r.label} (interaction)`, ...f });
    if (r.perf) {
      for (const f of (r.perf.regressions || [])) all.push({ where: `${r.label} (timing)`, ...f });
      for (const f of (r.perf.clsFindings || [])) all.push({ where: `${r.label} (timing)`, ...f });
    }
  }
  if (all.length) {
    L.push("## Findings");
    L.push("");
    for (const f of all.filter((x) => x.blocking)) L.push(`- **${f.where}** ${f.kind}: ${f.detail}`);
    for (const f of all.filter((x) => !x.blocking)) L.push(`- ${f.where} ${f.kind}: ${f.detail}`);
    L.push("");
  }
  const timed = result.routes.filter((r) => r.perf);
  if (timed.length) {
    const unthrottled = timed.filter((r) => !r.perf.throttled);
    L.push("## Timing");
    L.push("");
    L.push(`${perf.CONDITIONS.runs} cold runs per route at ${perf.CONDITIONS.viewport.width}px, ` +
           `CPU throttled ${perf.CONDITIONS.cpuThrottlingRate}x, network 1.6 Mbps / 150ms. Median ` +
           `first, range in brackets.`);
    L.push("");
    L.push("| Route | LCP ms | CLS | TBT ms | FCP ms | Transfer KB |");
    L.push("|---|---|---|---|---|---|");
    const cell = (s) => (s.median == null ? "not reported" : `${s.median} (${s.min}-${s.max})`);
    for (const r of timed) {
      L.push(`| ${r.label} | ${cell(r.perf.lcp)} | ${cell(r.perf.cls)} | ${cell(r.perf.tbt)} | ` +
             `${cell(r.perf.fcp)} | ${cell(r.perf.transferKB)} |`);
    }
    L.push("");
    /* The shift attribution, printed next to the number that caused the worry. A CLS total with no
     * named element sends the reader hunting, and layout shift only appears under throttling, so the
     * hunt usually fails on a fast browser and the number gets dismissed. */
    const shifty = timed.filter((r) => (r.perf.worstShifts || []).length &&
                                       r.perf.cls.median > perf.CLS_GOOD);
    if (shifty.length) {
      L.push("### What moved");
      L.push("");
      L.push("Layout shift appears on a slow connection and vanishes on a fast one, so these are");
      L.push("recorded during the throttled run rather than left for someone to reproduce by hand.");
      L.push("");
      for (const r of shifty) {
        L.push(`**${r.label}** (CLS ${r.perf.cls.median})`);
        L.push("");
        for (const s of r.perf.worstShifts) {
          L.push(`- \`${s.value}\` at ${s.at}ms: ${s.sources.join("; ") || "(no source recorded)"}`);
        }
        L.push("");
      }
    }

    L.push("**LCP and TBT are recorded, not graded.** Nothing here is compared to the 2.5s Core Web");
    L.push("Vitals threshold. That threshold matters where Google has field data, and the Chrome UX");
    L.push("Report has none for this origin on either device type, so it currently decides nothing.");
    L.push("The margin it was meant to settle was 3ms, and the range in each bracket above shows how");
    L.push("much larger ordinary run-to-run variance is than that.");
    L.push("");
    L.push(`A finding is raised only when a median moves past the recorded baseline by more than ` +
           `${Math.round((perf.REGRESSION.lcp.factor - 1) * 100)}% AND at least ` +
           `${perf.REGRESSION.lcp.floor}ms for LCP, which is the size of change that means someone ` +
           `shipped something heavy rather than that the machine was busy.`);
    L.push("");
    L.push(`**CLS is different, and does get an absolute threshold**: over ${perf.CLS_GOOD} is ` +
           `advisory, over ${perf.CLS_POOR} is blocking. The LCP argument does not transfer. That ` +
           `was a 3ms margin inside a 100ms spread; layout shift here was measured at 0.345 against ` +
           `a 0.1 target with four of six routes at exactly 0, so the margin is wide and the ` +
           `measurement is quiet. It is also not a proxy for a ranking signal: it is content moving ` +
           `under someone's finger as they reach for it, which is a defect whether or not Google is ` +
           `watching.`);
    if (!result.baseline) {
      L.push("");
      L.push("**No baseline was recorded when this ran**, so nothing above was compared to anything." +
             " Write one with `--perf --record-baseline`.");
    }
    if (unthrottled.length) {
      L.push("");
      L.push("**Throttling did not apply on " + unthrottled.map((r) => r.label).join(", ") +
             "**, so those timings describe this machine at full speed and are not comparable to " +
             "the rest.");
    }
    L.push("");
  }

  L.push("## What this run did NOT check");
  L.push("");
  L.push("Colour contrast (that is `tests/test_contrast.py`, which recomputes WCAG ratios from the");
  L.push("palette), screen-reader output as actually spoken, and anything on a route outside the six");
  L.push("above. Only these page-states were measured, and a clean result says nothing about the");
  L.push("other 6,542 pages.");
  L.push("");
  const skipped = result.routes.filter((r) => r.interactions && r.interactions.skipped);
  if (skipped.length) {
    L.push("Interactions were not driven on " +
      skipped.map((r) => `**${r.label}** (${r.interactions.skipped})`).join(", ") +
      ". Those routes are measured for layout only; nothing about their behaviour is established here.");
  }
  return L.join("\n");
}

async function main() {
  const live = flag("--live");
  const custom = valueOf("--url");
  let server = null, base;

  if (custom) base = custom.replace(/\/$/, "");
  else if (live) base = "https://truewise.dev";
  else {
    if (!fs.existsSync(path.join(SITE, "index.html"))) {
      console.error(`No built site at ${SITE}. Run \`make site\` or \`./preview-build.sh\` first, ` +
                    `or pass --live to check production.`);
      process.exit(2);
    }
    const s = await serve(SITE);
    server = s.server;
    base = `http://127.0.0.1:${s.port}`;
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const outDir = path.join(ROOT, `layout-check-${stamp}`);
  fs.mkdirSync(path.join(outDir, "screenshots"), { recursive: true });

  /* Load the recorded baseline BEFORE the run, so a regression is measured against something that
   * was written down rather than against whatever this run happens to produce. */
  let baseline = null;
  if (flag("--perf") && fs.existsSync(BASELINE)) {
    try {
      baseline = JSON.parse(fs.readFileSync(BASELINE, "utf8")).routes || null;
    } catch (e) {
      console.error(`perf_baseline.json could not be read (${e.message}); timings will be recorded ` +
                    `and nothing will be called a regression.`);
    }
  }

  let browser;
  try {
    browser = await chromium.launch({ headless: !flag("--open") });
  } catch (e) {
    /* The npm package installs without the browser binary, so this is the normal first-run state
     * rather than a broken machine. Say which command fixes it instead of printing a stack. */
    if (server) server.close();
    console.error(
      "Chromium could not start, so NOTHING was checked. This is not a pass.\n\n" +
      "  npx playwright install chromium\n\n" +
      `Underlying error: ${String(e).split("\n")[0]}`,
    );
    process.exit(2);
  }
  const result = {
    startedAt: new Date().toISOString(), base, states: 0, blocking: 0, advisory: 0, routes: [],
    baseline,
  };

  try {
    for (const route of ROUTES) {
      const entry = { label: route.label, path: route.path, widths: {}, interactions: {} };
      for (const w of WIDTHS) {
        const ctx = await browser.newContext({
          viewport: { width: w.width, height: w.height },
          deviceScaleFactor: 1,
          isMobile: w.mobile,
          hasTouch: w.mobile,
        });
        const page = await ctx.newPage();
        const url = base + route.path;
        const resp = await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });

        /* A 404 that gets measured and reported as clean is worse than a crash. */
        if (resp && resp.status() >= 400) {
          entry.widths[w.label] = { findings: [{ kind: "http", blocking: true,
            detail: `${url} returned ${resp.status()}, so nothing on this route was measured.` }] };
          result.blocking++;
          await ctx.close();
          continue;
        }

        const r = await page.evaluate(probe, {});
        /* The probe refuses to measure a zero-width viewport. If that happens under Playwright the
         * viewport was not applied, which invalidates the whole state rather than the page. */
        if (r.inconclusive) {
          entry.widths[w.label] = { findings: [{ kind: "inconclusive", blocking: true,
            detail: `${r.detail} Expected ${w.width}px.` }] };
          result.blocking++;
          await ctx.close();
          continue;
        }
        await page.screenshot({
          path: path.join(outDir, "screenshots", `${route.label}-${w.label}.png`),
          fullPage: true,
        });
        entry.widths[w.label] = r;
        result.states++;
        result.blocking += r.findings.filter((f) => f.blocking).length;
        result.advisory += r.findings.filter((f) => !f.blocking).length;

        /* Interactions run once per route, at the widest viewport, where every control is present.
         * Running them at all four would quadruple the time to re-prove the same code path. */
        if (w.label === "desktop") {
          entry.interactions = await interactions(page, route);
          result.blocking += (entry.interactions.findings || []).length;
          await page.screenshot({
            path: path.join(outDir, "screenshots", `${route.label}-after-interaction.png`),
            fullPage: true,
          });
        }
        await ctx.close();
      }
      if (flag("--perf")) {
        entry.perf = await measureRoute(browser, base, route, (m) => console.log(m));
        /* Two independent judgements. Regression is 'worse than it was'; the CLS threshold is
         * 'bad regardless of what it was', which a baseline comparison can never say, because a
         * baseline recorded on a bad day makes that day the standard. */
        const r = perf.regressions(route.label, entry.perf, (result.baseline || {})[route.label]);
        const c = perf.clsFindings(route.label, entry.perf);
        entry.perf.regressions = r;
        entry.perf.clsFindings = c;
        result.blocking += r.length + c.filter((f) => f.blocking).length;
        result.advisory += c.filter((f) => !f.blocking).length;
      }

      result.routes.push(entry);
      const b = Object.values(entry.widths).reduce(
        (n, s) => n + s.findings.filter((f) => f.blocking).length, 0);
      const t = entry.perf
        ? `  LCP ${entry.perf.lcp.median}ms (${entry.perf.lcp.min}-${entry.perf.lcp.max}), ` +
          `CLS ${entry.perf.cls.median}, TBT ${entry.perf.tbt.median}ms`
        : "";
      console.log(`${b ? "FAIL" : "ok  "}  ${route.label}${t}`);
    }
  } finally {
    await browser.close();
    if (server) server.close();
  }

  /* The refusal to claim a pass over nothing. */
  const expected = ROUTES.length * WIDTHS.length;
  if (result.states === 0) {
    console.error("\nINCONCLUSIVE: zero page-states were measured. This is not a pass.");
    process.exit(2);
  }

  fs.writeFileSync(path.join(outDir, "result.json"), JSON.stringify(result, null, 2));
  fs.writeFileSync(path.join(outDir, "report.md"), markdown(result));

  /* Recording a baseline is an explicit act, never a side effect of a run. If every run rewrote it,
   * a slow drift would move the baseline along with it and the comparison would always pass: the
   * check would be measuring itself. */
  if (flag("--perf") && flag("--record-baseline")) {
    const routes = {};
    for (const r of result.routes) {
      if (!r.perf) continue;
      routes[r.label] = {
        lcp: r.perf.lcp, cls: r.perf.cls, tbt: r.perf.tbt,
        fcp: r.perf.fcp, transferKB: r.perf.transferKB,
        throttled: r.perf.throttled,
      };
    }
    const unthrottled = Object.values(routes).filter((r) => !r.throttled);
    if (unthrottled.length) {
      console.error(`\nRefusing to record a baseline: throttling did not apply on ` +
                    `${unthrottled.length} route(s), so these numbers describe an unthrottled ` +
                    `machine and nothing could be honestly compared against them later.`);
      process.exit(2);
    }
    fs.writeFileSync(BASELINE, JSON.stringify({
      recordedAt: new Date().toISOString(),
      base, conditions: perf.CONDITIONS,
      note: "Recorded on one machine under fixed throttling. Comparable only to runs from the " +
            "same machine under the same conditions. Not a Core Web Vitals verdict.",
      routes,
    }, null, 2));
    console.log(`\nBaseline written to ${path.relative(ROOT, BASELINE)} for ` +
                `${Object.keys(routes).length} routes.`);
  }

  console.log(`\n${result.states} of ${expected} page-states measured.`);
  console.log(`${result.blocking} blocking, ${result.advisory} advisory.`);
  console.log(`Report: ${path.relative(ROOT, outDir)}/report.md`);

  if (result.states < expected) {
    console.error(`\nINCONCLUSIVE: ${expected - result.states} page-states did not run.`);
    process.exit(2);
  }
  process.exit(result.blocking ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
