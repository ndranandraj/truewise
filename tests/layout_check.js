#!/usr/bin/env node
/* The layout and interaction check: decision B.
 *
 *   node tests/layout_check.js              against the built site/ directory
 *   node tests/layout_check.js --live       against https://truewise.dev
 *   node tests/layout_check.js --url X      against any base URL, for a preview deploy
 *   node tests/layout_check.js --open       leave the browser visible
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

async function interactions(page, route) {
  const out = [];
  const findings = [];
  const before = await page.evaluate(tableState);
  if (before.rows == null) return { skipped: "no program table on this route", findings, steps: out };

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
    const icell = ix.skipped ? ix.skipped
      : ix.findings.length ? `**${ix.findings.length} blocking**`
      : `${ix.steps.map((s) => s.step).join(", ") || "none"}: clean`;
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
  }
  if (all.length) {
    L.push("## Findings");
    L.push("");
    for (const f of all.filter((x) => x.blocking)) L.push(`- **${f.where}** ${f.kind}: ${f.detail}`);
    for (const f of all.filter((x) => !x.blocking)) L.push(`- ${f.where} ${f.kind}: ${f.detail}`);
    L.push("");
  }
  L.push("## What this run did NOT check");
  L.push("");
  L.push("Colour contrast (that is `tests/test_contrast.py`, which recomputes WCAG ratios from the");
  L.push("palette), screen-reader output as actually spoken, and anything on a route outside the six");
  L.push("above. Only these page-states were measured, and a clean result says nothing about the");
  L.push("other 6,542 pages.");
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
      result.routes.push(entry);
      const b = Object.values(entry.widths).reduce(
        (n, s) => n + s.findings.filter((f) => f.blocking).length, 0);
      console.log(`${b ? "FAIL" : "ok  "}  ${route.label}`);
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
