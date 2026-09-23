// Value Check's search view has three states for its college list: loading, ready and failed.
//
// This runs the page's own scripts in jsdom with fetch stubbed, because the failure only exists in a
// browser: a blocked schools.json left the page on "Loading colleges" for good, with no message and
// no way on, and the label stayed "Loading colleges" even after a successful load. Neither shows up
// in a check that only looks at the page as served.
//
// Usage: node tests/value_check_states.js   (no built site needed: the college list is a fixture)
const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync("site/value-check/index.html", "utf8");
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)).map((m) => m[1]);
const app = inline.reduce((a, b) => (b.length > a.length ? b : a));
const search = fs.readFileSync("site/assets/college-search.js", "utf8");
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");

const FIXTURE = {
  schools: [
    { unitid: "223232", name: "Baylor University", city: "Waco", state: "TX" },
    { unitid: "110662", name: "University of California-Los Angeles", city: "Los Angeles", state: "CA" },
  ],
  benchmarks: {},
};

let failures = 0;
const check = (ok, msg) => {
  console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`);
  if (!ok) failures += 1;
};
const settle = () => new Promise((r) => setTimeout(r, 30));

async function main() {
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/value-check/" });
  const w = dom.window;
  let schoolsOk = false;
  w.fetch = async (url) => {
    if (String(url).includes("schools.json")) {
      if (!schoolsOk) return { ok: false, status: 503, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => FIXTURE };
    }
    return { ok: false, status: 404, json: async () => ({}) };
  };
  w.scrollTo = () => {};
  w.eval(search);
  w.eval(app);
  await settle();

  const d = w.document;
  const label = () => (d.querySelector('label[for="q"]') || {}).textContent || "";
  const count = () => (d.getElementById("rescount") || {}).textContent || "";

  // Failed: named, recoverable, and the query survives.
  d.getElementById("q").value = "baylor";
  d.getElementById("q").dispatchEvent(new w.Event("input"));
  await settle();
  check(label() === "College list did not load", `failed state names itself (label: "${label()}")`);
  check(/did not load/.test(count()), "failed state explains what happened");
  check(!!d.getElementById("vc-retry"), "failed state offers Retry");
  check(!!d.querySelector('#rescount a[href="/colleges/"]'), "failed state offers a browse route that needs no data");
  check(d.getElementById("q").value === "baylor", "the typed query is kept");
  check(!/Loading colleges/.test(count()), "typing after a failure does not revert to a loading message");

  // Retry succeeds: ready, and the label says so.
  schoolsOk = true;
  d.getElementById("vc-retry").click();
  await settle();
  check(label() === "Search 2 colleges by name", `ready state updates the label (label: "${label()}")`);
  check(!/did not load/.test(count()), "the failure message is gone once the list loads");

  if (failures) {
    console.error(`\n${failures} Value Check state check(s) failed`);
    process.exit(1);
  }
  console.log("\nValue Check loading, failed and ready states hold");
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
