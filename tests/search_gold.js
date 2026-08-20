// Gold-set gate for search ranking changes.
//
// Four smoke queries cannot approve a ranking change: ranking regressions are silent and only show
// up as "the search feels worse". This runs a versioned set of realistic queries (aliases, city
// intent, near-duplicate names, misspellings, no-result cases) against the real generated indexes and
// fails on any regression. Run before and after any change to the matcher.
//
// Usage: node tests/search_gold.js   (or `make test-search-gold`)
const fs = require("fs");

const GOLD = JSON.parse(fs.readFileSync("tests/search_gold_set.json", "utf8"));
const COLLEGES = JSON.parse(fs.readFileSync("site/value-check/data/schools.json", "utf8")).schools;
const K12 = JSON.parse(fs.readFileSync("site/k12/data/index.json", "utf8")).schools;
const TW = require("../site/assets/college-search.js");

let pass = 0;
const failures = [];

const record = (ok, label, detail) => {
  if (ok) pass++;
  else failures.push(`${label}\n      ${detail}`);
};

// ---- College ----
// Providers may expose either the legacy searchSchools(list, q) or a provider object; support both
// so the gold set can gate the migration itself.
const collegeSearch = (q, opts) =>
  TW.CollegeSearchProvider
    ? TW.CollegeSearchProvider.search(q, { data: COLLEGES, ...opts }).map((r) => r.title || r.name)
    : TW.searchSchools(COLLEGES, q).map((s) => s.name);

for (const t of GOLD.college) {
  const hits = collegeSearch(t.q);
  const label = `college  ${JSON.stringify(t.q).padEnd(38)} [${t.case}]`;
  if (t.none) {
    record(hits.length === 0, label, `expected no results, got ${hits.length}: ${hits.slice(0, 3)}`);
  } else if (t.top) {
    record(
      hits[0] && hits[0].includes(t.top),
      label,
      `expected top to contain ${JSON.stringify(t.top)}, got ${JSON.stringify(hits[0] || "(none)")}`,
    );
  } else if (t.within) {
    const slice = hits.slice(0, t.within);
    record(
      slice.some((n) => n.includes(t.expect)),
      label,
      `expected ${JSON.stringify(t.expect)} within first ${t.within}, got ${JSON.stringify(slice)}`,
    );
  }
}

// ---- K-12 ----
// Until K12SearchProvider lands, fall back to the current name-only filter so the gate shows the gap
// rather than silently passing.
// Normalise both shapes to a plain name string so the gate does not depend on which is in place.
const k12Search = (q, opts = {}) => {
  if (TW.K12SearchProvider) {
    return TW.K12SearchProvider.search(q, { data: K12, limit: 1e6, ...opts }).map((r) => r.title);
  }
  const term = q.toLowerCase();
  let out = K12.filter((s) => (s.n || "").toLowerCase().includes(term));
  if (opts.state) out = out.filter((s) => s.s === opts.state);
  return out.map((s) => s.n);
};

for (const t of GOLD.k12) {
  const label = `k12      ${JSON.stringify(t.q).padEnd(38)} [${t.case}]`;
  if (t.none) {
    const hits = k12Search(t.q);
    record(hits.length === 0, label, `expected no results, got ${hits.length}`);
  } else if (t.narrows) {
    const all = k12Search(t.q).length;
    const narrowed = k12Search(t.q, { state: t.state }).length;
    record(
      narrowed > 0 && narrowed < all,
      label,
      `state=${t.state} should narrow ${all} results, got ${narrowed}`,
    );
  } else if (t.within) {
    const slice = k12Search(t.q).slice(0, t.within);
    record(
      slice.some((n) => (n || "").toUpperCase().includes(t.expect.toUpperCase())),
      label,
      `expected ${JSON.stringify(t.expect)} within first ${t.within}, got ${JSON.stringify(slice)}`,
    );
  } else if (t.min_results) {
    const n = k12Search(t.q).length;
    record(n >= t.min_results, label, `expected at least ${t.min_results} matches, got ${n}`);
  }
}

const total = GOLD.college.length + GOLD.k12.length;
console.log(`search gold set v${GOLD.version}: ${pass}/${total} passed`);
if (failures.length) {
  console.log("\nFAILURES:");
  failures.forEach((f) => console.log("  " + f));
  process.exit(1);
}
console.log("ALL GOLD-SET CHECKS PASSED");
