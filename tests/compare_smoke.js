// Headless smoke test for site/compare/index.html against the real generated schools.json.
// Runs the page's actual JS in a minimal DOM stub and asserts rendered cells match the data.
// Usage: node tests/compare_smoke.js   (requires site/value-check/data/schools.json to exist)
const fs = require("fs");

const html = fs.readFileSync("site/compare/index.html", "utf8");
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const data = JSON.parse(fs.readFileSync("site/value-check/data/schools.json", "utf8")).schools;

const mk = () => ({
  innerHTML: "",
  value: "",
  textContent: "",
  style: {},
  addEventListener() {},
  querySelectorAll: () => [],
  querySelector: () => null,
  focus() {},
});
const els = {
  q: mk(),
  results: mk(),
  cmp: mk(),
  live: mk(),
  "income-row": mk(),
  income: Object.assign(mk(), { value: "-1" }),
};
global.document = { getElementById: (id) => els[id] || mk() };
global.window = { addEventListener() {} };
// The shared alias/search module both pickers load; inject it as the page would.
global.TWSearch = require("../site/assets/college-search.js");
// Record what the page does to history. Adding a school must PUSH, so each addition is a real
// navigation that analytics can see and the back button can undo; removing must REPLACE, or back
// would silently re-add a school someone just dismissed.
const HISTORY = [];
global.location = { search: "", pathname: "/compare/" };
const applyUrl = (url) => {
  const i = url.indexOf("?");
  global.location.search = i === -1 ? "" : url.slice(i);
};
global.history = {
  pushState(_s, _t, url) {
    HISTORY.push(["push", url]);
    applyUrl(url);
  },
  replaceState(_s, _t, url) {
    HISTORY.push(["replace", url]);
    applyUrl(url);
  },
};
global.fetch = async () => ({ json: async () => ({ schools: data }) });
global.setTimeout = (f) => f();
global.clearTimeout = () => {};
// Real enough to read back what the page just wrote, which is what applyFromUrl() parses.
global.URLSearchParams = class {
  constructor(qs) {
    this.p = new Map(
      String(qs || "")
        .replace(/^\?/, "")
        .split("&")
        .filter(Boolean)
        .map((kv) => kv.split("=").map(decodeURIComponent)),
    );
  }
  get(k) {
    return this.p.has(k) ? this.p.get(k) : null;
  }
};

eval(js);

const txt = () => els.cmp.innerHTML.replace(/<[^>]*>/g, "|").replace(/\|+/g, "|");
let fails = 0;
const ck = (name, cond) => {
  console.log((cond ? "PASS  " : "FAIL  ") + name);
  if (!cond) fails++;
};

(async () => {
  await add("223232"); // Baylor University
  await add("110538"); // California State University-Chico
  let o = txt();
  ck("Baylor pass rate 97% of 64 measured", /97%.*of 64 measured/.test(o));
  ck("Chico pass rate 100% of 66 measured", /100%.*of 66 measured/.test(o));
  ck("net price averages 41,104 and 14,480", o.includes("$41,104") && o.includes("$14,480"));
  ck("state thresholds 34,809 and 36,976", o.includes("$34,809") && o.includes("$36,976"));
  ck("Pell 12% and 43%", o.includes("12%") && o.includes("43%"));
  ck("completion 80% and 63%", o.includes("80%") && o.includes("63%"));
  ck("enrollment 14,785 and 13,631", o.includes("14,785") && o.includes("13,631"));
  ck("links to pre-rendered college page", /href="\/college\/baylor-university\//.test(els.cmp.innerHTML));

  els.income.value = "0"; // Under $30k
  render();
  o = txt();
  ck("income selector reprices to under-30k (22,024 / 9,902)", o.includes("$22,024") && o.includes("$9,902"));
  ck("row label switches to per-income", o.includes("Net price at this income"));
  els.income.value = "-1";
  render();

  // Distinct removable schools is the observable proxy for the internal picked[] list. Counting
  // occurrences of data-rm would double now: each school gets a Remove control in the desktop
  // table header AND in the phone card list, and only one of the two is displayed at a width.
  const cols = () =>
    new Set(
      Array.from(els.cmp.innerHTML.matchAll(/data-rm="([^"]+)"/g), (m) => m[1]),
    ).size;

  ck("duplicate add is ignored", (await add("223232"), cols() === 2));

  const others = data.filter((s) => s.n_pass + s.n_fail > 5 && s.unitid !== "223232" && s.unitid !== "110538");
  for (const s of others.slice(0, 5)) await add(s.unitid);
  ck("maximum of 4 schools enforced", cols() === 4);

  remove("223232");
  ck("remove works", cols() === 3);

  const thin = data.find((s) => !s.net_price && s.n_pass + s.n_fail >= 1);
  if (thin) {
    await add(thin.unitid);
    ck("school without net price shows 'not reported'", txt().includes("not reported"));
  }

  // Escaping, observed: a school name containing "&" must render as "&amp;", not raw.
  const amp = data.find((s) => (s.name || "").includes("&") && s.n_pass + s.n_fail >= 1);
  if (amp) {
    await add(amp.unitid);
    const h = els.cmp.innerHTML;
    // The escaped form must be present, and no bare "&" from the name may survive.
    ck(
      "school name with & is HTML-escaped",
      h.includes(amp.name.replace(/&/g, "&amp;")) && !h.includes(amp.name),
    );
  }

  // The advertised aliases must resolve in Compare's picker (the audit's "UCLA" defect).
  const topName = (query) => {
    const hits = TWSearch.searchSchools(data, query);
    return hits[0] ? hits[0].name : "(none)";
  };
  ck('Compare resolves "UCLA" (advertised on the page)', topName("ucla").includes("California-Los Angeles"));
  ck('Compare resolves "Baylor" to the University', topName("baylor") === "Baylor University");
  ck('Compare resolves "ut austin" to UT Austin', topName("ut austin").includes("Texas at Austin"));

  // The phone presentation. The sticky-label table was the interim repair and it failed its own
  // acceptance: at 320px one school still overflowed the 280px content box, and with two or more
  // schools a fragment of the outgoing column sat between the sticky label and the next full
  // column, so a phone user read partial words and partial numbers. Below 700px the table is
  // replaced by metric-major cards, which removes the horizontal axis and keeps the schools
  // adjacent, since stacking one school per card would put the two compared figures a scroll apart.
  await add("223232");
  await add("110538");
  const out = els.cmp.innerHTML;
  const metrics = (out.match(/<section class="cmp-metric">/g) || []).length;
  // Minus the header row, whose first cell is the empty corner above the metric labels.
  const tableRows = (out.match(/<tr><th>/g) || []).length - 1;
  ck("phone view exists", out.includes('class="cmp-stack"'));
  ck(
    `one card per metric (${metrics} cards vs ${tableRows} table rows)`,
    metrics > 0 && metrics === tableRows,
  );

  // Same numbers in both renderings, or the phone view is quietly a different product.
  const picked2 = new Set(
    Array.from(out.matchAll(/data-rm="([^"]+)"/g), (m) => m[1]),
  );
  const cells = Array.from(out.matchAll(/<tr><th>[^<]*<\/th>(.*?)<\/tr>/g), (m) =>
    Array.from(m[1].matchAll(/<td>(.*?)<\/td>/g), (c) => c[1]),
  ).flat();
  const dds = Array.from(out.matchAll(/<dd>(.*?)<\/dd>/g), (m) => m[1]);
  ck(
    `every table value appears in the phone view (${cells.length} cells, ${dds.length} entries)`,
    cells.length > 0 && cells.length === dds.length && cells.every((c, i) => c === dds[i]),
  );
  ck(
    `each card names every school it lists (${picked2.size} schools)`,
    picked2.size > 1 && (out.match(/<dt>/g) || []).length === metrics * picked2.size,
  );

  /* History behaviour. Compare used replaceState throughout, which does not register as a
     navigation, so additions and completed comparisons were invisible to analytics that only see
     pageviews. Adding pushes; removing replaces, or the back button would re-add a school someone
     just dismissed. This is the measurement itself, so it is asserted rather than assumed. */
  // Reset through the page's own code path rather than by reaching into its state.
  global.location.search = "";
  await applyFromUrl();
  HISTORY.length = 0;
  await add("223232");
  ck("adding a school pushes a history entry", HISTORY.at(-1)[0] === "push");
  ck("the pushed URL carries the school", HISTORY.at(-1)[1] === "?schools=223232");
  await add("110538");
  ck(
    "a completed two-school comparison is a single URL",
    HISTORY.at(-1)[0] === "push" && HISTORY.at(-1)[1] === "?schools=223232,110538",
  );
  remove("110538");
  ck("removing replaces rather than pushes", HISTORY.at(-1)[0] === "replace");
  remove("223232");
  ck("emptying returns to the bare path", HISTORY.at(-1)[1] === "/compare/");

  // A shared link must not manufacture one history entry per school: init used to replay add()
  // per id, so opening a four-school link buried the referring page four steps back.
  HISTORY.length = 0;
  global.location.search = "?schools=223232,110538";
  await applyFromUrl();
  ck("a shared link restores both schools", cols() === 2);
  ck("a shared link pushes nothing", HISTORY.length === 0);

  // And back must rebuild the comparison, not just the address bar.
  global.location.search = "?schools=223232";
  await applyFromUrl();
  ck("going back rebuilds the comparison", cols() === 1 && txt().includes("Baylor"));

  console.log(fails ? "\n" + fails + " FAILURE(S)" : "\nALL COMPARE CHECKS PASSED");
  process.exit(fails ? 1 : 0);
})();
