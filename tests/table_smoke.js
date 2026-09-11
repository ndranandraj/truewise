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
const { ProgramTable, COLUMNS } = window.TWTable;

const rows = [
  { program: "Computer Science", credential: "Master's", earnings: 195622, premium: 161809, verdict: "pass", debt: 20500, payback: 0.1, completers: 2416 },
  { program: "Mechanical Eng", credential: "Bachelor's", earnings: 99955, premium: 66142, verdict: "pass", horizon: "1yr_after_completion", debt: 22500, payback: 0.3, completers: 421 },
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
check(/could be assessed/.test($(".tw-table__coverage").textContent), "coverage should say 'could be assessed'");
check(/35% have an earnings verdict/.test($(".tw-table__coverage").textContent), "coverage percent/wording wrong");

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

// 6b. The 1-year earnings value carries an inline marker; the 4-year values do not.
check($$(".tw-oneyr").length === 1, "exactly one 1-year marker expected (only the 1-year row)");
check(/1-year earnings/.test(root.textContent), "1-year earnings label text missing");

// 7. Sort by earnings: rows reorder, insufficient sinks to the bottom, aria-sort updates.
earningsTh.querySelector(".tw-th__sort").click();
const after = $$("tbody .tw-td--program").map((th) => th.textContent);
check(after[after.length - 1] === "Philosophy", "insufficient row should sink to the bottom on sort");
check(after[0] === "Computer Science", "descending earnings should put the highest first");
const earningsTh2 = $$(".tw-th").find((th) => /Median earnings/.test(th.textContent));
check(earningsTh2.getAttribute("aria-sort") === "descending", "aria-sort should be descending after first click");
// Focus must survive the re-render: it should land on the same sort button, not the body.
check(
  document.activeElement === earningsTh2.querySelector(".tw-th__sort"),
  "focus should be restored to the sort button after sorting",
);

// 8. Toggle direction.
earningsTh2.querySelector(".tw-th__sort").click();
const th3 = $$(".tw-th").find((th) => /Median earnings/.test(th.textContent));
check(th3.getAttribute("aria-sort") === "ascending", "second click should flip to ascending");
const asc = $$("tbody .tw-td--program").map((x) => x.textContent);
check(asc[asc.length - 1] === "Philosophy", "insufficient still sinks on ascending sort");

// 9. The 1-year marker survives sorting (each re-render must reattach it, like the static row).
check($$(".tw-oneyr").length === 1, "1-year marker lost after sorting");

// 10. The mobile sort control exists, is labelled, and offers exactly the sortable columns.
//
// The header row is display:none below 768px. It used to be clipped to 1px instead, which left its
// six sort buttons in the tab order: a keyboard user on a phone tabbed through six controls that
// were not on screen. Sorting has to live somewhere visible at that width, so it lives here.
const sortSel = document.querySelector(".tw-sort__select");
check(!!sortSel, "a visible mobile sort control must exist");
const sortLabel = document.querySelector(".tw-sort__label");
check(!!sortLabel && sortLabel.getAttribute("for") === sortSel.id, "sort select needs its own label");
check(!!sortSel.id, "sort select needs an id so the label can point at it");
const sortableKeys = COLUMNS.filter((c) => c.sortable !== false).map((c) => c.key);
const optKeys = Array.from(sortSel.options).map((o) => o.value).filter(Boolean);
check(
  optKeys.join(",") === sortableKeys.join(","),
  `sort options ${optKeys} should be the sortable columns ${sortableKeys}`,
);

// 11. The control actually sorts, and returning to "Table order" restores the source order.
// Sort by program name: alphabetical differs from the earnings order left behind by check 8, so a
// no-op would be visible. Numeric columns here happen to rank the same way earnings does.
const asSupplied = rows.map((r) => r.program);
const beforeMobileSort = $$("tbody .tw-td--program").map((x) => x.textContent);
sortSel.value = "program";
sortSel.dispatchEvent(new dom.window.Event("change"));
const byName = $$("tbody .tw-td--program").map((x) => x.textContent);
check(byName.join() !== beforeMobileSort.join(), "choosing a column in the mobile control should reorder");
check(byName[0] === "Computer Science", "program sort should start A to Z");
check(byName[byName.length - 1] === "Philosophy", "insufficient still sinks under the mobile sort");
check(
  document.activeElement === document.querySelector(".tw-sort__select"),
  "focus should return to the sort select after its re-render",
);
const dirBtn = document.querySelector(".tw-sort__dir");
check(!!dirBtn, "an active sort needs a visible direction toggle");
dirBtn.click();
const flipped = $$("tbody .tw-td--program").map((x) => x.textContent);
check(flipped.join() !== byName.join(), "the direction toggle should flip the order");
const sel2 = document.querySelector(".tw-sort__select");
sel2.value = "";
sel2.dispatchEvent(new dom.window.Event("change"));
check(
  $$("tbody .tw-td--program").map((x) => x.textContent).join() === asSupplied.join(),
  "Table order should restore the order the rows were supplied in",
);
check(!document.querySelector(".tw-sort__dir"), "no direction toggle when no column is sorted");


/* ---- Search, filters and progressive reveal (Wave 1) ----------------------------------------
 * A Penn State profile renders 150 stacked rows about 47,000px tall on a phone, which is a data
 * dump rather than an interface. These narrow the set before the reveal limit does. The honesty
 * rules bite hardest here: nothing may be hidden by DEFAULT, suppressed rows must survive every
 * operation, and every count must be stated against the whole set, never the visible slice.
 */
const many = [];
for (let i = 0; i < 45; i++) {
  const insuf = i % 5 === 0;
  many.push({
    program: (i % 3 === 0 ? "Nursing " : "History ") + i,
    credential: i % 2 ? "Bachelor's" : "Master's",
    earnings: insuf ? null : 40000 + i * 100,
    premium: insuf ? null : i * 100,
    verdict: insuf ? "insufficient" : i % 4 === 1 ? "fail" : "pass",
    debt: insuf ? null : 20000,
    payback: insuf ? null : 2,
    completers: 50 + i,
  });
}
const host = document.createElement("div");
document.body.appendChild(host);
new ProgramTable(host, { rows: many, coverage: { measured: 36, total: 45 } });
const $$$ = (sel) => Array.from(host.querySelectorAll(sel));
const shownNames = () => $$$("tbody .tw-td--program").map((x) => x.textContent);
const countText = () => host.querySelector(".tw-table__count").textContent;

check(shownNames().length === 20, `opening view reveals 20 of 45, got ${shownNames().length}`);
check(/Showing 20 of 45 programs/.test(countText()), `count states the whole set: ${countText()}`);
check(
  $$$("tbody .tw-verdict--insuf").length > 0,
  "suppressed programs must appear in the DEFAULT view, not be filtered away",
);

for (const suffix of ["-q", "-v", "-c"]) {
  const field = host.querySelector(`[id$="${suffix}"]`);
  check(!!field, `control ${suffix} exists`);
  if (!field) continue;
  const label = host.querySelector(`label[for="${field.id}"]`);
  check(!!label && label.textContent.trim().length > 0, `control ${suffix} carries a visible label`);
}

host.querySelector(".tw-more").click();
check(shownNames().length === 40, `Show more reveals another page, got ${shownNames().length}`);
check(/Showing 40 of 45/.test(countText()), `the count follows the reveal: ${countText()}`);

const qEl = host.querySelector('[id$="-q"]');
qEl.value = "nursing";
qEl.dispatchEvent(new dom.window.Event("input"));
const nursing = shownNames();
check(nursing.length > 0 && nursing.every((n) => /Nursing/.test(n)), "search filters to matches");
check(/of 45 programs match/.test(countText()), `search counts against the total: ${countText()}`);
check(
  document.activeElement === host.querySelector('[id$="-q"]'),
  "focus stays in the search box, or a second keystroke would land on body",
);

qEl.value = "";
qEl.dispatchEvent(new dom.window.Event("input"));
const vEl = host.querySelector('[id$="-v"]');
vEl.value = "insufficient";
vEl.dispatchEvent(new dom.window.Event("change"));
const insufShown = $$$("tbody .tw-verdict--insuf").length;
check(
  insufShown === shownNames().length && insufShown === 9,
  `the suppressed filter isolates all 9, got ${insufShown} of ${shownNames().length}`,
);
check(/9 of 45 programs match/.test(countText()), `filters count honestly: ${countText()}`);

vEl.value = "";
vEl.dispatchEvent(new dom.window.Event("change"));
check(shownNames().length === 20, "clearing a filter resets the reveal to one page");

// The tail assertions below await a fetch, so they live in an async main. This file is CommonJS
// (require, not import), where top-level await is not available.
async function main() {
  /* ---------------------------------------------------------------------------
   * The progressive tail, which is the half of this component that was wrong.
   *
   * 245 profiles ship 150 rows and keep the rest behind a fetch. Search, the two filters and every
   * sort ran over the loaded rows only, while the count line reported against the full total. So a
   * search for "nursing" on Penn State examined 150 of 489 programs and announced its result as "3 of
   * 489 programs match", which is a claim about 339 rows this code had never read. Sorting had the
   * same shape: the top of the loaded slice presented as the top of the list. And the Degree menu was
   * built from the loaded rows, so a credential appearing only in the tail was not offered at all.
   *
   * These assert the repair and, more importantly, the disclosure when the repair cannot happen.
   * -------------------------------------------------------------------------*/
  const tailRows = [];
  for (let i = 0; i < 6; i++)
    tailRows.push({
      program: `Tail Program ${i}`,
      credential: "Doctorate", // a credential that exists ONLY in the tail
      earnings: 300000 + i,
      premium: 260000,
      verdict: "pass",
      debt: 1000,
      payback: 0.1,
      completers: 10,
    });

  function tailTable(onMore) {
    const h = document.createElement("div");
    document.body.appendChild(h);
    const inst = new ProgramTable(h, {
      rows: many.slice(0, 10),
      coverage: { measured: 8, total: 16 },
      remaining: tailRows.length,
      onMore,
    });
    return { h, inst, count: () => h.querySelector(".tw-table__count").textContent };
  }

  // A resolving tail: interaction loads it, and the whole set is then searched and sorted.
  {
    let calls = 0;
    const { h, inst, count } = tailTable(() => {
      calls++;
      return Promise.resolve(tailRows);
    });

    check(/Showing 10 of 16 programs/.test(count()), `reveal wording is fine pre-fetch: ${count()}`);
    check(
      !/Doctorate/.test(h.querySelector('[id$="-c"]').innerHTML),
      "the Degree menu cannot offer a tail-only credential before the tail is loaded",
    );

    // focusin, not input: the menu has to be complete before it is opened, not after a choice.
    h.querySelector(".tw-filters").dispatchEvent(
      new dom.window.Event("focusin", { bubbles: true }),
    );
    check(calls === 1, "focusing a filter starts the tail fetch");

    await new Promise((r) => setTimeout(r, 0));
    check(inst.rows.length === 16, `the tail is merged, got ${inst.rows.length}`);
    check(inst.remaining === 0, "remaining drops to zero once merged");
    check(/All 16 programs/.test(count()), `count reflects the whole set: ${count()}`);
    check(
      /Doctorate/.test(h.querySelector('[id$="-c"]').innerHTML),
      "the Degree menu gains the tail-only credential once loaded",
    );

    // And the interaction that matters: a search now reaches rows that were in the tail.
    const q = h.querySelector('[id$="-q"]');
    q.value = "Tail Program";
    q.dispatchEvent(new dom.window.Event("input"));
    const names = [...h.querySelectorAll("tbody .tw-td--program")].map((x) => x.textContent);
    check(names.length === 6, `search reaches the tail, matched ${names.length} of 6`);
    check(/6 of 16 programs match/.test(count()), `and counts what it searched: ${count()}`);

    // Sorting descending by earnings must surface the tail rows, which are the highest paid. Before
    // the fix this returned the top of the loaded slice and called it the top.
    q.value = "";
    q.dispatchEvent(new dom.window.Event("input"));
    const earnBtn = [...h.querySelectorAll(".tw-th__sort")].find((b) => b.dataset.key === "earnings");
    earnBtn.click();
    const top = h.querySelector("tbody .tw-td--program").textContent;
    check(/Tail Program/.test(top), `sort covers the tail, top row was ${top}`);
    check(calls === 1, "the tail is fetched once, not once per keystroke");
  }

  // A failing tail: the count line must shrink its denominator and name the gap.
  {
    const { h, count } = tailTable(() => Promise.reject(new Error("offline")));
    const q = h.querySelector('[id$="-q"]');
    q.value = "nursing";
    q.dispatchEvent(new dom.window.Event("input"));
    await new Promise((r) => setTimeout(r, 0));
    const text = count();
    check(!/of 16 programs match/.test(text), `a failed tail must not claim 16 were searched: ${text}`);
    check(/of the 10 programs loaded match/.test(text), `states the set it searched: ${text}`);
    check(
      /6 more could not be loaded/.test(text) && /not been searched/.test(text),
      `names the gap as a gap: ${text}`,
    );
  }

  /* Focus after "Show more" goes to the first new row, not the button.
   *
   * The button sits below the rows it reveals, so focusing it skipped a keyboard user past the content
   * they asked for. Worse, on the final click the button is removed because nothing is left to reveal,
   * so there was nothing to focus and focus fell to <body>: the user was thrown to the top of the
   * document at the moment they finished opening the list. */
  {
    const h = document.createElement("div");
    document.body.appendChild(h);
    new ProgramTable(h, { rows: many.slice(0, 25), coverage: { measured: 20, total: 25 } });
    const firstNewName = [...h.querySelectorAll("tbody .tw-tr")].length; // index 20 after reveal
    h.querySelector(".tw-more").click();
    const rowsNow = [...h.querySelectorAll("tbody .tw-tr")];
    check(rowsNow.length === 25, `all 25 revealed on the last click, got ${rowsNow.length}`);
    check(h.querySelector(".tw-more") === null, "the button is gone, so it cannot be the destination");
    check(
      document.activeElement === rowsNow[firstNewName],
      "focus lands on the first newly revealed row",
    );
    check(
      document.activeElement !== document.body,
      "and never on <body>, which would return the reader to the top of the page",
    );
    check(
      rowsNow[firstNewName].getAttribute("tabindex") === "-1",
      "the landing row is focusable without becoming a tab stop",
    );
    check(
      /5 more programs shown/.test(h.querySelector(".tw-table__status").textContent),
      "the reveal is announced with how many arrived",
    );
  }
}

main().then(() => {
  console.log(`table smoke (B5 program table): ${pass}/${pass + fail.length} passed`);
  if (fail.length) {
    fail.forEach((f) => console.log("  FAIL: " + f));
    process.exit(1);
  }
  console.log("ALL TABLE CHECKS PASSED");
});
