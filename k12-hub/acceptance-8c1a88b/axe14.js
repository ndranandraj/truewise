// PR #14 accessibility scan on the built page (axe-core, WCAG 2.2 A/AA and best practice).
// 6 October: each state must return HTTP 200 and show its intended content first; populated and
// no-match searches added.
const path = require("path"), fs = require("fs");
const pw = require(path.join(process.cwd(), "node_modules", "playwright"));
const AXE = fs.readFileSync(path.join(process.cwd(), "node_modules/axe-core/axe.min.js"), "utf8");
(async () => {
  const b = await pw.chromium.launch(); let bad = 0;
  console.log("Chromium", b.version(), "| axe-core", JSON.parse(fs.readFileSync("node_modules/axe-core/package.json", "utf8")).version);
  // Each state must load (HTTP 200) and show its intended content before it is scanned, so an
  // error or loading page cannot be recorded as a clean scan.
  const STATES = [
    ["/k12/", async (p) => (await p.textContent("h1")).includes("What does your high school offer?")],
    ["/k12/advanced-courses/", async (p) => !!(await p.$("#q")) && (await p.textContent("h1")).includes("Advanced courses")],
    ["/k12/advanced-courses/?school=170993000942", async (p) => (await p.textContent("h1")).trim() === "LANE TECHNICAL HIGH SCHOOL"],
    ["/k12/advanced-courses/?school=362058002877", async (p) => (await p.textContent("h1")).trim() === "STUYVESANT HIGH SCHOOL"],
    ["/k12/advanced-courses/?q=international", async (p) => (await p.$$(".school-card")).length > 0],
    ["/k12/advanced-courses/?q=zzqxv", async (p) => (await p.textContent("#rescount")).includes("No high schools match")],
  ];
  for (const [u, ready] of STATES) for (const w of [390, 1280]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    const resp = await p.goto("http://localhost:8787" + u, { waitUntil: "load" });
    let loaded = false;
    for (let i = 0; i < 40 && !loaded; i++) { loaded = await ready(p).catch(() => false); if (!loaded) await p.waitForTimeout(250); }
    if (!resp || resp.status() !== 200 || !loaded) {
      bad++;
      console.log(`FAIL  ${u} at ${w}px: not scanned (HTTP ${resp ? resp.status() : "none"}, intended content ${loaded ? "present" : "missing"})`);
      await p.close();
      continue;
    }
    await p.addScriptTag({ content: AXE });
    const v = await p.evaluate(async () => (await axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"] })).violations.map((x) => `${x.id}(${x.nodes.length})`));
    if (v.length) bad++;
    console.log(`${v.length ? "FAIL" : "ok  "}  ${u} at ${w}px: HTTP 200, content loaded, ${v.join(" ") || "no violations"}`);
    await p.close();
  }
  await b.close();
  const f = await pw.firefox.launch(); console.log("Firefox", f.version()); await f.close();
  process.exit(bad ? 1 : 0);
})();
