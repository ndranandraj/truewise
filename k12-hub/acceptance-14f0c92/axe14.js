// PR #14 accessibility scan on the built page (axe-core, WCAG 2.2 A/AA and best practice).
const path = require("path"), fs = require("fs");
const pw = require(path.join(process.cwd(), "node_modules", "playwright"));
const AXE = fs.readFileSync(path.join(process.cwd(), "node_modules/axe-core/axe.min.js"), "utf8");
(async () => {
  const b = await pw.chromium.launch(); let bad = 0;
  console.log("Chromium", b.version(), "| axe-core", JSON.parse(fs.readFileSync("node_modules/axe-core/package.json", "utf8")).version);
  for (const u of ["/k12/", "/k12/advanced-courses/", "/k12/advanced-courses/?school=170993000942", "/k12/advanced-courses/?school=362058002877"]) for (const w of [390, 1280]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    await p.goto("http://localhost:8787" + u, { waitUntil: "load" }); await p.waitForTimeout(1500);
    await p.addScriptTag({ content: AXE });
    const v = await p.evaluate(async () => (await axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa", "best-practice"] })).violations.map((x) => `${x.id}(${x.nodes.length})`));
    if (v.length) bad++;
    console.log(`${v.length ? "FAIL" : "ok  "}  ${u} at ${w}px: ${v.join(" ") || "no violations"}`);
    await p.close();
  }
  await b.close();
  const f = await pw.firefox.launch(); console.log("Firefox", f.version()); await f.close();
  process.exit(bad ? 1 : 0);
})();
