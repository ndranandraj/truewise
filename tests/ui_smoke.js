// Behavioural smoke for the smaller Stage 3 components (ui.js), under jsdom.
// Folded into `make test-components`. Validates the 0.4 pass/fail items for B3/B4/B6/B8/B9/B11/B12/B13.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const dom = new JSDOM(`<!doctype html><body>
  <div id="chips"></div><p id="chips-live" role="status"></p>
  <div id="filters"></div><p id="filters-live" role="status"></p>
  <details class="tw-disclosure" id="disc"><summary>How we count</summary><div class="tw-disclosure__body">Method.</div></details>
</body>`);
const { window } = dom;
global.window = window;
global.document = window.document;

const src = fs.readFileSync(path.join(__dirname, "..", "components", "ui.js"), "utf8");
new window.Function(src).call(window);
const UI = window.TWUI;

let pass = 0;
const fail = [];
const check = (c, m) => (c ? pass++ : fail.push(m));

// B8 status pill carries text, never colour alone.
check(/clears the bar/.test(UI.statusPill("pass")), "pass pill missing text");
check(/falls short/.test(UI.statusPill("fail")), "fail pill missing text");
check(/insufficient data/.test(UI.statusPill("insufficient")), "insufficient pill missing text");

// B6 coverage note: computed percent, low-coverage flag under 50%.
check(/89 of 254/.test(UI.coverageNote(89, 254)), "coverage numbers wrong");
check(/35% have earnings data/.test(UI.coverageNote(89, 254)), "coverage percent wrong");
check(/tw-coverage--low/.test(UI.coverageNote(89, 254)), "low coverage (35%) should be flagged");
check(!/tw-coverage--low/.test(UI.coverageNote(200, 254)), "high coverage should not be flagged");

// B14 suppressed + B7 source.
check(/insufficient data/.test(UI.suppressed()), "suppressed text missing");
check(/Source: College Scorecard, release 2026-06-10/.test(
  UI.sourceNote({ source: "College Scorecard", release: "2026-06-10" }),
), "source note format wrong");

// B3 empty state routes onward, never a dead end.
const empty = UI.emptyState("zzz", [{ href: "/colleges/", label: "Browse by state" }]);
check(/No matches for/.test(empty) && /Browse by state/.test(empty), "empty state missing query or route");

// B12 loading skeleton is announced and reserves space.
check(/aria-busy="true"/.test(UI.skeleton()) && /aria-live="polite"/.test(UI.skeleton()), "skeleton not announced");

// B13 error is a role=alert with a way forward.
const err = UI.errorState("Could not load.", { href: "#", label: "Retry" });
check(/role="alert"/.test(err) && /Retry/.test(err), "error state missing alert role or retry");

// B4 state chips: aria-pressed toggles, narrowing announced.
const chipsLive = document.getElementById("chips-live");
let picked = "start";
const chips = new UI.StateChips(document.getElementById("chips"), {
  states: [["IN", 21], ["IL", 17]], total: 194, live: chipsLive,
  onPick: (st) => (picked = st),
});
const inChip = [...document.getElementById("chips").querySelectorAll(".tw-chip")].find((b) => b.dataset.st === "IN");
inChip.click();
check(inChip.getAttribute("aria-pressed") === "true", "picked chip should be aria-pressed");
check(picked === "IN", "onPick did not fire with the state");
check(/Narrowed to IN/.test(chipsLive.textContent), "narrowing not announced");

// B9 filters: change announces the count returned by onChange.
const fLive = document.getElementById("filters-live");
const filters = new UI.Filters(document.getElementById("filters"), {
  sorts: [{ key: "earnings", label: "Earnings" }, { key: "program", label: "Program" }],
  live: fLive,
  onChange: (state) => (state.showInsufficient ? 254 : 89),
});
filters.toggle.click(); // hide insufficient
check(/89 programs shown/.test(fLive.textContent), "filter change did not announce the count");

// B11 disclosure: Escape collapses and returns focus to summary.
const disc = UI.enhanceDisclosure(document.getElementById("disc"));
disc.open = true;
disc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
check(disc.open === false, "Escape should collapse the disclosure");

console.log(`ui smoke (B3/B4/B6/B7/B8/B9/B11/B12/B13/B14): ${pass}/${pass + fail.length} passed`);
if (fail.length) {
  fail.forEach((f) => console.log("  FAIL: " + f));
  process.exit(1);
}
console.log("ALL UI CHECKS PASSED");
