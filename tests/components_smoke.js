// Behavioural smoke for the Stage 3 search combobox shell (component B1), under jsdom.
//
// Manual smoke like the other node tests (search/compare/embed): run with `make test-components`.
// Requires jsdom (`npm install jsdom`). Not in CI, which runs the Python suite; this validates the
// interaction contract the a11y matrix in 0.4 requires: ARIA combobox state, keyboard navigation,
// selection, the live-region count, and Escape behaviour.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const dom = new JSDOM(`<!doctype html><body><div id="root"></div></body>`, {
  runScripts: "outside-only",
});
const { window } = dom;
global.window = window;
global.document = window.document;

// Load the shell into the jsdom window.
const src = fs.readFileSync(path.join(__dirname, "..", "components", "search.js"), "utf8");
new window.Function(src).call(window);
const { SearchCombobox } = window.TWSearchUI;

// A tiny fake provider so the test does not depend on the data files.
const DATA = [
  { id: 1, title: "University of California-Berkeley", meta: "Berkeley, CA", why: "name" },
  { id: 2, title: "Baylor University", meta: "Waco, TX", why: "city" },
  { id: 3, title: "Boston College", meta: "Chestnut Hill, MA" },
];
const provider = {
  search: (q, opts) =>
    DATA.filter((d) => d.title.toLowerCase().includes(q.toLowerCase())).slice(0, opts.limit),
};

let selected = null;
const root = document.getElementById("root");
const cb = new SearchCombobox(root, {
  provider,
  data: DATA,
  label: "Find a college",
  minChars: 1, // the three fixture titles share no 2-char substring; keep the query simple
  onSelect: (r) => (selected = r),
});

const input = root.querySelector(".tw-search__input");
const list = root.querySelector(".tw-search__list");
const status = root.querySelector(".tw-search__status");

let pass = 0;
const fail = [];
const check = (cond, msg) => (cond ? pass++ : fail.push(msg));

// Synchronously run a query (bypass the debounce timer).
function type(v) {
  input.value = v;
  cb._run();
}
function key(k) {
  input.dispatchEvent(new window.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
}

// 1. ARIA wiring present before any input.
check(input.getAttribute("role") === "combobox", "input is not role=combobox");
check(input.getAttribute("aria-expanded") === "false", "aria-expanded should start false");
check(list.getAttribute("role") === "listbox", "list is not role=listbox");
check(status.getAttribute("aria-live") === "polite", "status is not a polite live region");

// 2. Typing opens the list, sets expanded, announces a count.
type("b");
check(list.hidden === false, "list should be visible after typing");
check(input.getAttribute("aria-expanded") === "true", "aria-expanded should be true when open");
check(list.querySelectorAll(".tw-search__opt").length === 3, "expected 3 options for 'b'");
check(/3 results/.test(status.textContent), `status should announce 3 results, got "${status.textContent}"`);

// 3. Options carry option semantics and the match reason.
const first = list.querySelector(".tw-search__opt");
check(first.getAttribute("role") === "option", "row is not role=option");
check(/matched on name/.test(first.textContent), "match reason not shown");

// 4. Keyboard: Down activates first option and sets aria-activedescendant (focus stays in input).
key("ArrowDown");
check(cb.active === 0, "ArrowDown should activate the first option");
check(input.getAttribute("aria-activedescendant") === first.id, "activedescendant not set to active option");
check(first.getAttribute("aria-selected") === "true", "active option should be aria-selected");

// 5. Down wraps, Up wraps back; Enter selects the active option.
key("ArrowDown"); key("ArrowDown"); // now index 2
check(cb.active === 2, "ArrowDown did not advance to index 2");
key("ArrowDown"); // wrap to 0
check(cb.active === 0, "ArrowDown should wrap to 0");
key("ArrowUp"); // wrap to last
check(cb.active === 2, "ArrowUp should wrap to last");
key("Enter");
check(selected && selected.id === 3, "Enter did not select the active option");
check(list.hidden === true, "list should close after selection");
check(input.value === "Boston College", "input should show the selected title");

// 6. No-result state announces and shows the empty markup.
type("zzzz");
check(/No results/.test(status.textContent), "no-result count not announced");
check(/No matches/.test(list.textContent), "empty state markup missing");

// 7. Escape closes an open list.
type("b");
check(list.hidden === false, "list should be open");
key("Escape");
check(list.hidden === true, "Escape should close the list");
check(input.getAttribute("aria-expanded") === "false", "aria-expanded should be false after Escape");

console.log(`components smoke (B1 search combobox): ${pass}/${pass + fail.length} passed`);
if (fail.length) {
  fail.forEach((f) => console.log("  FAIL: " + f));
  process.exit(1);
}
console.log("ALL COMPONENT CHECKS PASSED");
