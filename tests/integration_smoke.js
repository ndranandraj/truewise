// Integration smoke: the composed K-12 flow (search + state chips + provider state filter), the one
// the report found broken because no test booted it. Loads the SAME three modules the fixture loads,
// wires them the SAME way, and drives a repeated-name query through narrowing. Under jsdom.
// Manual smoke, folded into `make test-components`.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const dom = new JSDOM(`<!doctype html><body>
  <div id="k12"></div><div id="k12-chips"></div><p id="k12-live" role="status"></p>
</body>`);
const { window } = dom;
global.window = window;
global.document = window.document;

const load = (rel) => new window.Function(fs.readFileSync(path.join(__dirname, "..", rel), "utf8")).call(window);
load("site/assets/college-search.js"); // TWSearch (providers)
load("components/search.js"); // TWSearchUI (combobox)
load("components/ui.js"); // TWUI (StateChips etc.)

const K12 = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "site/k12/data/index.json"), "utf8")).schools;

let pass = 0;
const fail = [];
const check = (c, m) => (c ? pass++ : fail.push(m));

// Replicate the fixture wiring exactly (this is what actually exercises the namespaces).
let k12State = null;
const chipsHost = document.getElementById("k12-chips");
const k12Live = document.getElementById("k12-live");
const box = new window.TWSearchUI.SearchCombobox(document.getElementById("k12"), {
  provider: window.TWSearch.K12SearchProvider,
  data: K12,
  label: "Find a high school",
  minChars: 3,
  providerOpts: () => ({ state: k12State }),
  onSelect: () => {},
});

let threw = null;
function renderChips() {
  const q = box.input.value.trim();
  if (q.length < 3) { chipsHost.innerHTML = ""; return; }
  const states = window.TWSearch.K12SearchProvider.statesFor(q, { data: K12 });
  const total = states.reduce((n, [, c]) => n + c, 0);
  if (states.length > 1 && total > 12) {
    // The exact call the report caught: must be TWUI.StateChips, not TWSearchUI.StateChips.
    new window.TWUI.StateChips(chipsHost, {
      states: states.slice(0, 8), total, live: k12Live,
      onPick: (st) => { k12State = st; box.refresh(); },
    });
  } else chipsHost.innerHTML = "";
}

// 1. A repeated name renders chips without throwing.
try {
  box.input.value = "central high school";
  box._run();
  renderChips();
} catch (e) {
  threw = e;
}
check(threw === null, `composed flow threw: ${threw && threw.message}`);
const chips = chipsHost.querySelectorAll(".tw-chip");
check(chips.length > 1, `expected state chips to render, got ${chips.length}`);

// 2. Before narrowing the visible results span multiple states (the reason narrowing exists).
//    (The list is capped at the combobox limit, so assert on state spread, not raw count.)
const statesBefore = new Set(box.results.map((r) => r.raw.s));
check(statesBefore.size > 1, `expected matches across states before narrowing, got ${[...statesBefore]}`);

// 3. Picking a state narrows the results to that state and announces it.
const inChip = [...chips].find((b) => b.dataset.st === "IN");
check(!!inChip, "expected an IN chip among the states");
if (inChip) {
  inChip.click(); // sets k12State=IN, calls box.refresh()
  const narrowed = box.results;
  check(narrowed.length > 0, "narrowing to IN should still return results");
  check(narrowed.every((r) => r.raw.s === "IN"), "narrowed results should all be in IN");
  check(/Narrowed to IN/.test(k12Live.textContent), "state narrowing not announced");
}

console.log(`integration smoke (composed K-12 flow): ${pass}/${pass + fail.length} passed`);
if (fail.length) {
  fail.forEach((f) => console.log("  FAIL: " + f));
  process.exit(1);
}
console.log("ALL INTEGRATION CHECKS PASSED");
