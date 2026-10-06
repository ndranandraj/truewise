// College Compare, the sequences a reader goes through: search, add, remove, Back and Forward.
//
// Runs the page's own scripts in jsdom with a five-college fixture (no built site needed). Two
// defects found in review of PR #16 (October 2026) are pinned here as complete sequences:
//   1. After a college was removed, a search still on screen kept it marked "already in the
//      comparison" and disabled. Results must follow every selection change, Back and Forward
//      included.
//   2. Back from four colleges left focus on the hidden four-college note (so on <body> in a
//      browser) and the live region still said "4 of 4 colleges selected". Focus must move to the
//      search, and the announcement must match the restored selection.
//
// Usage: node tests/compare_states.js
const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync("site/compare/index.html", "utf8");
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)).map((m) => m[1]);
const app = inline.reduce((a, b) => (b.length > a.length ? b : a));
const search = fs.readFileSync("site/assets/college-search.js", "utf8");
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");

const college = (unitid, name, city, state) => ({
  unitid, name, city, state, control: "Public", threshold: 35000, enrollment: 10000,
  n_programs: 10, n_pass: 6, n_fail: 1, n_insufficient: 3,
  n_ug_programs: 8, n_ug_pass: 5, n_ug_fail: 1, n_insuff_ug: 2, n_insuff_grad: 1,
  net_price: { avg: 20000, brackets: [10000, 12000, 15000, 20000, 30000] },
  pell: 0.3, completion: 0.7, hidden_gem: false,
});
const SCHOOLS = [
  college("223232", "Baylor University", "Waco", "TX"),
  college("110662", "University of California-Los Angeles", "Los Angeles", "CA"),
  college("150987", "Ivy Tech Community College", "Indianapolis", "IN"),
  college("131520", "Howard University", "Washington", "DC"),
  college("140553", "Morehouse College", "Atlanta", "GA"),
];
const MAP = Object.fromEntries(SCHOOLS.map((s) => [s.unitid, s.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")]));

let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`); if (!ok) failures += 1; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// A fresh page for each sequence, so a failure in one cannot cause failures in the other.
async function open() {
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/compare/", pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = async (url) => ({
    ok: true, status: 200,
    json: async () => (String(url).includes("slug-map.json") ? MAP : { schools: SCHOOLS }),
  });
  w.eval(search);
  w.eval(app);
  await wait(50);
  const d = w.document;
  const q = d.getElementById("q"), live = d.getElementById("live"), full = d.getElementById("full");
  const type = async (text) => { q.value = text; q.dispatchEvent(new w.Event("input")); await wait(250); };
  const result = (name) => [...d.querySelectorAll("#results button.res")].find((b) => b.textContent.includes(name));
  const picks = () => [...d.querySelectorAll(".pick__name")].map((n) => n.textContent);
  const back = async () => { w.history.back(); await wait(150); };
  const forward = async () => { w.history.forward(); await wait(150); };
  const add = async (term, name) => {
    await type(term);
    const b = result(name);
    if (!b || b.disabled) throw new Error(`no selectable result for ${name}`);
    b.click();
    await wait(30);
  };
  return { w, d, q, live, full, type, result, picks, back, forward, add };
}

async function main() {
  // ---- 1. Results follow the selection: Remove, Back, Forward ----
  {
  const { d, type, result, picks, back, forward, add } = await open();
  await add("baylor", "Baylor University");
  await type("baylor");
  let b = result("Baylor University");
  check(b && b.disabled && /already in the comparison/.test(b.textContent), "Baylor, once added, is marked and disabled in a new search");
  d.querySelector('.pick__rm[data-rm="223232"]').click();
  await wait(30);
  b = result("Baylor University");
  check(!d.querySelector("table.cmp") && picks().length === 0, "removing Baylor empties the comparison");
  check(b && !b.disabled && !/already in the comparison/.test(b.textContent),
    "with Baylor removed, the search still on screen offers it again");
  b.click();
  await wait(30);
  check(picks().join() === "Baylor University", "and selecting it adds Baylor back");

  await add("howard", "Howard University");
  await type("howard");
  check(result("Howard University").disabled, "Howard is marked while selected");
  await back(); // Back undoes adding Howard
  check(picks().join() === "Baylor University", "Back undoes the addition of Howard");
  check(result("Howard University") && !result("Howard University").disabled, "after Back, the search on screen offers Howard again");
  await forward();
  check(picks().join() === "Baylor University,Howard University", "Forward restores Howard");
  check(result("Howard University") && result("Howard University").disabled, "after Forward, Howard is marked again");
  }

  // ---- 2. Back from four: focus and the announcement ----
  {
  const { d, q, live, full, picks, back, forward, add } = await open();
  await add("baylor", "Baylor University");
  await add("howard", "Howard University");
  await add("ucla", "University of California-Los Angeles");
  await add("ivy tech", "Ivy Tech Community College");
  check(picks().length === 4 && d.activeElement === full && !full.hidden, "at four, the note replaces the search and has focus");
  check(/4 of 4 colleges selected/.test(live.textContent), `the fourth addition is announced ("${live.textContent}")`);
  await back();
  check(picks().length === 3, "Back from four leaves three");
  check(full.hidden && !d.getElementById("add-box").hidden, "the note goes and the search returns");
  check(d.activeElement === q, `focus moves to the search, not the hidden note or the page (focus: ${d.activeElement.id || d.activeElement.tagName})`);
  check(live.textContent === "3 of 4 colleges selected.", `the announcement matches the restored selection ("${live.textContent}")`);
  await forward();
  check(picks().length === 4 && d.activeElement === full, "Forward to four moves focus from the hidden search to the note");
  check(live.textContent === "4 of 4 colleges selected.", `and says so ("${live.textContent}")`);
  // Back to none says so too.
  for (let i = 0; i < 6; i += 1) await back();
  check(picks().length === 0 && live.textContent === "No colleges selected.", `Back to an empty comparison says so ("${live.textContent}")`);
  }

  if (failures) { console.error(`\n${failures} Compare state check(s) failed`); process.exit(1); }
  console.log("\nCompare search marks, Back and Forward focus and announcements hold");
}
main().catch((e) => { console.error(e); process.exit(1); });
