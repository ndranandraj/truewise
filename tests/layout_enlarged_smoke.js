// The layout check's enlarged-text pass must never report clean when it did not reach the page it
// meant to measure (October 2026 review). Fake pages force each failure; jsdom checks headerProbe on a
// page with no header.
//
// Usage: node tests/layout_enlarged_smoke.js
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const { ENLARGED_WIDTHS, enlargedPass } = require("./layout_enlarged.js");

let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`); if (!ok) failures += 1; };

// A fake page: `goto` behaviour and which selectors render are set per case; evaluate() records calls.
function fakePage({ gotoThrows = false, status = 200, noResponse = false, renders = [".site-header"] } = {}) {
  const calls = [];
  return {
    calls,
    async goto() {
      calls.push("goto");
      if (gotoThrows) throw new Error("page.goto: net::ERR_CONNECTION_REFUSED\nCall log: ...");
      return noResponse ? null : { status: () => status };
    },
    async waitForSelector(sel) {
      calls.push(`wait ${sel}`);
      if (!renders.includes(sel)) throw new Error(`page.waitForSelector: Timeout 10000ms exceeded waiting for ${sel}`);
    },
    async evaluate(fn) { calls.push(`evaluate ${fn.name}`); return fn.name === "probe" ? { findings: [{ kind: "x", blocking: true, detail: "probe ran" }] } : undefined; },
    async waitForTimeout() {},
  };
}
function doubleText() {}
function probe() {}
const opts = (extra) => ({ probes: [probe], doubleText, ...extra });
const blocking = (f, kind) => f.length === 1 && f[0].blocking === true && f[0].kind === kind;

async function main() {
  check(ENLARGED_WIDTHS.some((w) => w.width === 769), "the enlarged pass covers 769px, where the Careers degree table overflowed");

  let p = fakePage({ gotoThrows: true });
  let f = await enlargedPass(p, "http://x/careers/", opts());
  check(blocking(f, "enlarged-load-failed") && !p.calls.some((c) => c.startsWith("evaluate")), "a navigation error is a blocking finding, and nothing is measured");

  p = fakePage({ status: 500 });
  f = await enlargedPass(p, "http://x/careers/", opts());
  check(blocking(f, "enlarged-load-failed") && /returned 500/.test(f[0].detail), "an error status is a blocking finding");

  p = fakePage({ noResponse: true });
  f = await enlargedPass(p, "http://x/", opts());
  check(blocking(f, "enlarged-load-failed"), "no response at all is a blocking finding");

  p = fakePage({ renders: [] });
  f = await enlargedPass(p, "http://x/", opts());
  check(blocking(f, "enlarged-not-ready") && /\.site-header/.test(f[0].detail) && !p.calls.some((c) => c.startsWith("evaluate")), "a missing header is a blocking finding, and nothing is measured");

  p = fakePage({ renders: [".site-header"] });
  f = await enlargedPass(p, "http://x/careers/?field=1107&cred=5", opts({ ready: [".cred-table"] }));
  check(blocking(f, "enlarged-not-ready") && /\.cred-table/.test(f[0].detail), "a route's ready selector that never renders (the Careers degree table) is a blocking finding");

  p = fakePage({ renders: [".site-header", ".cred-table"] });
  f = await enlargedPass(p, "http://x/careers/?field=1107&cred=5", opts({ ready: [".cred-table"] }));
  check(f.length === 1 && f[0].detail === "probe ran" && p.calls.indexOf("evaluate doubleText") > p.calls.indexOf("wait .cred-table"), "when the page is ready, text is doubled after it renders and the probes' findings are returned");

  // headerProbe on a page with no header: a blocking finding, not an empty (clean) result.
  const dom = new JSDOM("<!doctype html><body><main><h1>No header here</h1></main></body>", { runScripts: "outside-only" });
  dom.window.eval(fs.readFileSync(path.join(__dirname, "layout_probe.js"), "utf8") + ";window.headerProbe = headerProbe;");
  const hp = dom.window.headerProbe();
  check(hp.findings.length === 1 && hp.findings[0].blocking && hp.findings[0].kind === "header-enlarged-missing", "headerProbe reports a missing header as blocking");

  if (failures) { console.error(`\n${failures} enlarged-pass check(s) failed`); process.exit(1); }
  console.log("\nEnlarged-text pass fails loudly when it cannot measure");
}
main().catch((e) => { console.error(e); process.exit(1); });
