// K-12 Compare, exercised after schools are added: the state the layout check never reached.
//
// Runs the page's own scripts in jsdom with a two-school fixture. Checks that Remove is a real,
// school-named button, that focus lands somewhere real after each removal, and that a staffing count
// a school did not report reads "Not reported" rather than "No".
//
// Usage: node tests/k12_compare_states.js   (no built site needed)
const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync("site/k12/compare/index.html", "utf8");
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)).map((m) => m[1]);
const app = inline.reduce((a, b) => (b.length > a.length ? b : a));
const search = fs.readFileSync("site/assets/college-search.js", "utf8");
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");

const courses = { offered: true };
const school = (name, police) => ({
  name, district: "District", state: "NY", enroll: 3000,
  courses: { calc: courses, phys: courses, chem: courses, cs: courses, ap: courses, ib: courses, dual: courses, gt: courses },
  staff: { counselor_ratio: 300, no_counselor: false, police, guard: true, uncert_pct: 2 },
});
const INDEX = { schools: [
  { k: "a", n: "Stuyvesant High School", d: "District", s: "NY" },
  { k: "b", n: "Lane Technical High School", d: "District", s: "NY" },
] };
const STATE = { a: school("Stuyvesant High School", true), b: school("Lane Technical High School", null) };

let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`); if (!ok) failures += 1; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/k12/compare/" });
  const w = dom.window;
  w.fetch = async (url) => ({
    ok: true, status: 200,
    json: async () => (String(url).includes("index.json") ? INDEX : STATE),
  });
  w.eval(search);
  w.eval(app);
  const d = w.document;
  const q = d.getElementById("q");
  const addByName = async (text) => {
    q.value = text;
    q.dispatchEvent(new w.Event("input"));
    await wait(250);
    const hit = d.querySelector("#results button[data-k]");
    if (!hit) throw new Error(`no search result for ${text}`);
    hit.click();
    await wait(30);
  };
  await addByName("stuyvesant");
  await addByName("lane technical");

  const rms = [...d.querySelectorAll("#cmp .rm")];
  check(rms.length === 2, `two remove controls (found ${rms.length})`);
  check(rms.every((b) => b.tagName === "BUTTON" && b.type === "button"), "every Remove is a real button");
  check(/Remove Stuyvesant High School/.test(rms[0].getAttribute("aria-label") || ""), "Remove is named for its school");

  const staffRow = [...d.querySelectorAll("#cmp tbody tr")].find((tr) => /Police/.test(tr.textContent));
  const cells = staffRow ? [...staffRow.querySelectorAll("td")].map((td) => td.textContent.trim()) : [];
  check(cells[0] === "Yes" && cells[1] === "Not reported", `unreported police reads "Not reported" (got ${JSON.stringify(cells)})`);
  check(!!(staffRow && staffRow.querySelector("td[data-label='Lane Technical High School']")),
    "each cell carries its school name for the phone card layout");

  rms[0].focus();
  rms[0].click();
  await wait(10);
  const left = d.querySelector("#cmp .rm");
  check(!!left && d.activeElement === left, "after a removal, focus moves to the next school's Remove");
  left.click();
  await wait(10);
  check(d.activeElement === q, "after the last removal, focus returns to the search box");

  if (failures) { console.error(`\n${failures} K-12 Compare check(s) failed`); process.exit(1); }
  console.log("\nK-12 Compare remove controls, focus and unknowns hold");
}
main().catch((e) => { console.error(e); process.exit(1); });
