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
global.history = { replaceState() {} };
global.location = { search: "", pathname: "/compare/" };
global.fetch = async () => ({ json: async () => ({ schools: data }) });
global.setTimeout = (f) => f();
global.clearTimeout = () => {};
global.URLSearchParams = class {
  constructor() {}
  get() {
    return null;
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

  // Column count is the observable proxy for the internal picked[] list.
  const cols = () => (els.cmp.innerHTML.match(/data-rm=/g) || []).length;

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

  console.log(fails ? "\n" + fails + " FAILURE(S)" : "\nALL COMPARE CHECKS PASSED");
  process.exit(fails ? 1 : 0);
})();
