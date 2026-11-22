// The homepage search suggestions (Prototype Q): their states, which exist only in a browser.
//
// Runs the homepage's own scripts in jsdom with the college list stubbed. What it guards:
//   * the list loads on first use, not with the page, and loads even if the box was focused before
//     the script arrived (no focus event to hear);
//   * a failed load says so and points to Search, never "Loading colleges" for good (the defect Value
//     Check once had), and the next keystroke tries again;
//   * Enter on a suggestion navigates; Enter with nothing chosen is left to the form.
// The navigation's target is checked in a real browser by the layout check's homepage-suggestions
// route.
//
// Usage: node tests/home_search_states.js   (no built site needed: the college list is a fixture)
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const html = fs.readFileSync("site/index.html", "utf8");
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");
const SRC = {
  matcher: fs.readFileSync("site/assets/college-search.js", "utf8"),
  combobox: fs.readFileSync("components/search.js", "utf8"),
  home: fs.readFileSync("site/assets/home-search.js", "utf8"),
};
const ROWS = [
  ["Baylor University", "Waco", "TX", 20000, "baylor-university"],
  ["University of Mary Hardin-Baylor", "Belton", "TX", 3500, "university-of-mary-hardin-baylor"],
  ["Baylor College of Medicine", "Houston", "TX", 0, "baylor-college-of-medicine"],
];

let failures = 0;
const check = (ok, msg) => {
  console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`);
  if (!ok) failures += 1;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// The page as served, with the three suggestion scripts in order and no inline script for them.
const tags = Array.from(html.matchAll(/<script[^>]*src="([^"]+)"[^>]*><\/script>/g)).map((m) => m[0]);
const srcs = tags.map((t) => t.match(/src="([^"]+)"/)[1]);
const order = ["/assets/college-search.js", "/components/search.js", "/assets/home-search.js"];
check(order.every((s) => srcs.includes(s)), "the homepage loads the matcher, the combobox and the suggestions script");
check(
  srcs.indexOf(order[0]) < srcs.indexOf(order[1]) && srcs.indexOf(order[1]) < srcs.indexOf(order[2]),
  "the suggestions script loads after what it uses",
);
check(order.every((s) => tags.find((t) => t.includes(s)).includes(" defer")), "each is deferred, so the page renders first");
check(/<form class="h-search" action="\/value-check\/" method="get" role="search" data-index="\/college\/search-index\.json">/.test(html),
  "the form still submits to Value Check and names the college list");

function boot({ respond, focusFirst = false }) {
  const nav = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => { if (/navigation/i.test(String(e.message))) nav.push(e.message); });
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/", virtualConsole: vc });
  const w = dom.window;
  const calls = [];
  w.fetch = (url) => {
    calls.push(url);
    return respond(calls.length);
  };
  w.eval(SRC.matcher);
  w.eval(SRC.combobox);
  const input = w.document.getElementById("h-q");
  if (focusFirst) input.focus();
  w.eval(SRC.home);
  const status = () => (w.document.querySelector(".h-search [role=status]") || {}).textContent || "";
  const options = () => Array.from(w.document.querySelectorAll(".h-search [role=option]")).map((o) => o.textContent.replace(/\s+/g, " ").trim());
  const type = async (v) => {
    input.value = v;
    input.dispatchEvent(new w.Event("input", { bubbles: true }));
    await sleep(220);
  };
  const key = (k) => {
    const e = new w.KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true });
    input.dispatchEvent(e);
    return e;
  };
  return { w, input, calls, status, options, type, key, nav };
}
const ok = (rows) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(rows) });
const fail = () => Promise.resolve({ ok: false, status: 503, json: () => Promise.reject(new Error("no")) });

(async () => {
  // Ready: nothing loads with the page; first focus loads it once; typing suggests.
  const a = boot({ respond: () => ok(ROWS) });
  check(a.calls.length === 0, "nothing loads with the page");
  a.input.focus();
  await sleep(20);
  check(a.calls.length === 1 && a.calls[0] === "/college/search-index.json", "first focus loads the college list");
  a.input.blur();
  a.input.focus();
  await sleep(20);
  check(a.calls.length === 1, "a second focus does not load it again");
  await a.type("baylor");
  check(a.options().length === 3 && a.options()[0].startsWith("Baylor University"), `typing suggests colleges, got ${JSON.stringify(a.options())}`);
  check(a.status() === "3 colleges. Use the arrow keys to choose one.", `the count is announced, got "${a.status()}"`);
  check(a.input.getAttribute("aria-expanded") === "true", "the combobox says it is expanded");
  const none = a.key("Enter");
  check(!none.defaultPrevented, "Enter with nothing chosen is left to the form (it searches Value Check)");
  a.key("ArrowDown");
  const one = a.key("Enter");
  await sleep(20);
  check(one.defaultPrevented && a.nav.length === 1, "Enter on a suggestion navigates, and does not submit the form");
  await a.type("zzzz");
  check(/No college matches/.test(a.w.document.querySelector(".h-search").textContent), "no match says so and offers a way on");
  check(a.w.document.querySelector('.h-search .tw-search__empty a[href="/colleges/"]'), "the no-match message links the state lists");

  // Focused before the script arrived: no focus event to hear, so it loads at start-up.
  const b = boot({ respond: () => ok(ROWS), focusFirst: true });
  await sleep(20);
  check(b.calls.length === 1, "a box focused before the script arrived still loads the list");

  // Typing before any focus event: the first keystroke loads it.
  const c = boot({ respond: () => ok(ROWS) });
  await c.type("baylor");
  await sleep(50);
  check(c.calls.length === 1 && c.options().length === 3, "the first keystroke loads the list and then suggests");

  // Failed: says so and points to Search; the next keystroke tries again and recovers.
  const d = boot({ respond: (n) => (n === 1 ? fail() : ok(ROWS)) });
  await d.type("baylor");
  await sleep(50);
  check(d.status() === "Suggestions did not load. Press Search to look the college up.", `a failed load says so, got "${d.status()}"`);
  check(!/Loading/.test(d.status()), "a failed load never stays on Loading");
  await d.type("baylo");
  await sleep(50);
  check(d.calls.length === 2, "the next keystroke tries again");
  check(d.options().length >= 1, "and the suggestions appear once it loads");

  console.log(failures ? `${failures} homepage search state checks failed` : "ALL HOMEPAGE SEARCH STATE CHECKS PASSED");
  process.exit(failures ? 1 : 0);
})();
