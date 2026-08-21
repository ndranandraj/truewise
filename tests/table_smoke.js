// Behavioural smoke for the Stage 3 program table (component B5), under jsdom.
// Manual smoke like the others: `make test-components` runs it. Validates the 0.4 B5 pass/fail list:
// coverage first, real table semantics, sortable columns with aria-sort, suppressed rows kept visible
// and sunk to the bottom, decorative premium bar with the number as real content, and per-cell labels
// for the mobile layout.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const dom = new JSDOM(`<!doctype html><body><div id="root"></div></body>`);
const { window } = dom;
global.window = window;
global.document = window.document;

const src = fs.readFileSync(path.join(__dirname, "..", "components", "table.js"), "utf8");
new window.Function(src).call(window);
const { ProgramTable } = window.TWTable;

const rows = [
  { program: "Computer Science", credential: "Master's", earnings: 195622, premium: 161809, verdict: "pass", debt: 20500, payback: 0.1, completers: 2416 },
  { program: "Mechanical Eng", credential: "Bachelor's", earnings: 99955, premium: 66142, verdict: "pass", debt: 22500, payback: 0.3, completers: 421 },
  { program: "Fine Arts", credential: "Bachelor's", earnings: 28900, premium: -4913, verdict: "fail", debt: 24000, payback: 6.4, completers: 88 },
  { program: "Philosophy", credential: "Bachelor's", earnings: null, premium: null, verdict: "insufficient", debt: null, payback: null, completers: 41 },
];

const root = document.getElementById("root");
const t = new ProgramTable(root, { rows, coverage: { measured: 89, total: 254 }, baseline: 33813, caption: "Programs" });

let pass = 0;
const fail = [];
const check = (c, m) => (c ? pass++ : fail.push(m));
const $ = (s) => root.querySelector(s);
const $$ = (s) => [...root.querySelectorAll(s)];

// 1. Coverage stated first, computed correctly.
check(/89 of 254/.test($(".tw-table__coverage").textContent), "coverage line missing/incorrect");
check(/35% have earnings data/.test($(".tw-table__coverage").textContent), "coverage percent wrong");

// 2. Real table semantics.
check($("table.tw-table") !== null, "no real <table>");
check($("caption") !== null, "no <caption>");
check($$('th[scope="col"]').length >= 6, "column headers missing scope=col");
check($$('th[scope="row"]').length === 4, "row headers (program) missing scope=row");

// 3. Sortable columns expose aria-sort; non-sortable (Degree, Verdict) do not.
const earningsTh = $$(".tw-th").find((th) => /Median earnings/.test(th.textContent));
check(earningsTh.getAttribute("aria-sort") === "none", "sortable col should start aria-sort=none");
const degreeTh = $$(".tw-th").find((th) => th.textContent.trim() === "Degree");
check(!degreeTh.hasAttribute("aria-sort"), "non-sortable col should not have aria-sort");

// 4. Suppressed row is visible and shows insufficient data, not 0/blank.
const insufRow = $(".tw-tr--insuf");
check(insufRow !== null, "insufficient row not rendered");
check(/insufficient data/.test(insufRow.textContent), "suppressed cells should say insufficient data");
// No cell in a suppressed row may be empty or render a bare 0 (the "unknown shown as 0" bug).
const emptyOrZero = [...insufRow.children].some((cell) => {
  const txt = cell.textContent.trim();
  return txt === "" || txt === "0" || txt === "$0";
});
check(!emptyOrZero, "suppressed cell must not render 0 or blank");

// 5. Every data cell carries a data-label for the mobile stacked layout.
const labelled = $$(".tw-td, th.tw-td").every((td) => td.hasAttribute("data-label"));
check(labelled, "a cell is missing data-label (mobile layout would drop its column)");

// 6. Premium bar is decorative; the signed number is real text.
const premBar = $(".tw-prem__bar");
check(premBar.getAttribute("aria-hidden") === "true", "premium bar must be aria-hidden");
check(/\+\$161,809/.test(root.textContent), "premium value not shown as text");

// 7. Sort by earnings: rows reorder, insufficient sinks to the bottom, aria-sort updates.
earningsTh.querySelector(".tw-th__sort").click();
const after = $$("tbody .tw-td--program").map((th) => th.textContent);
check(after[after.length - 1] === "Philosophy", "insufficient row should sink to the bottom on sort");
check(after[0] === "Computer Science", "descending earnings should put the highest first");
const earningsTh2 = $$(".tw-th").find((th) => /Median earnings/.test(th.textContent));
check(earningsTh2.getAttribute("aria-sort") === "descending", "aria-sort should be descending after first click");

// 8. Toggle direction.
earningsTh2.querySelector(".tw-th__sort").click();
const th3 = $$(".tw-th").find((th) => /Median earnings/.test(th.textContent));
check(th3.getAttribute("aria-sort") === "ascending", "second click should flip to ascending");
const asc = $$("tbody .tw-td--program").map((x) => x.textContent);
check(asc[asc.length - 1] === "Philosophy", "insufficient still sinks on ascending sort");

console.log(`table smoke (B5 program table): ${pass}/${pass + fail.length} passed`);
if (fail.length) {
  fail.forEach((f) => console.log("  FAIL: " + f));
  process.exit(1);
}
console.log("ALL TABLE CHECKS PASSED");
