// The High Schools lookup's status messages, through a whole search sequence (October 2026).
//
// No match used to be a list item: shown, but outside the status region (role="status"), so a screen
// reader was never told. Review of PR #14 found it. It must now be said in the status region and only
// there, and the region must follow the query as it changes and is cleared, so it never keeps saying
// "No high schools match" for text that is gone.
//
// Runs the page's own scripts in jsdom with a small index (no built site needed).
// Usage: node tests/k12_lookup_states.js
const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync("site/k12/advanced-courses/index.html", "utf8");
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)).map((m) => m[1]);
const app = inline.reduce((a, b) => (b.length > a.length ? b : a));
const search = fs.readFileSync("site/assets/college-search.js", "utf8");
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");

const school = (k, n, s) => ({ k, n, s, d: "District", ap: true, c: true, p: true });
const INDEX = { schools: [
  school("1", "LANE TECHNICAL HIGH SCHOOL", "IL"),
  school("2", "STUYVESANT HIGH SCHOOL", "NY"),
  school("3", "INTERNATIONAL ACADEMY", "MI"),
] };

let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`); if (!ok) failures += 1; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/k12/advanced-courses/" });
  const w = dom.window;
  w.fetch = async () => ({ ok: true, status: 200, json: async () => INDEX });
  w.eval(search);
  w.eval(app);
  await wait(80);
  const d = w.document;
  const q = d.getElementById("q"), status = d.getElementById("rescount"), results = d.getElementById("results");
  check(status && status.getAttribute("role") === "status" && status.getAttribute("aria-live") === "polite", "the result count is a polite status region");
  const type = async (text) => { q.value = text; q.dispatchEvent(new w.Event("input")); await wait(250); };
  const listText = () => results.textContent.replace(/\s+/g, " ").trim();

  await type("zzqxv");
  check(status.textContent === "No high schools match “zzqxv”.", `no match is said in the status region ("${status.textContent}")`);
  check(!/No high schools match/.test(listText()) && !results.querySelector("li"), "and not shown a second time in the list");

  await type("lane");
  check(status.textContent === "1 school", `a new query replaces it with the count ("${status.textContent}")`);
  check(!!results.querySelector(".school-card"), "and its result is listed");

  await type("zzqxv");
  await type("");
  check(status.textContent === "", `clearing the field clears the status ("${status.textContent}")`);
  check(/Type at least three letters/.test(listText()), "and the list shows the instruction again");

  await type("zzqxv");
  await type("zz");
  check(status.textContent === "", `under three letters the old no-match is not left behind ("${status.textContent}")`);

  if (failures) { console.error(`\n${failures} High Schools lookup check(s) failed`); process.exit(1); }
  console.log("\nHigh Schools lookup status messages follow the query");
}
main().catch((e) => { console.error(e); process.exit(1); });
