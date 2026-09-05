/* Find search gaps from the data, never from watching anyone search.
 *
 * Zero-result and wrong-result searches are the best evidence for a missing alias, and the obvious
 * way to get them is to log what visitors type. This project chose not to: the site's whole claim
 * is that it does not collect what it does not need, and a search box is the most sensitive input
 * on it. So the gaps are derived instead. For each large institution, ask the colloquial forms a
 * person would plausibly type and check whether that institution comes back first.
 *
 * This is a REPORT, not a gate. Most failures it prints are genuine ambiguity rather than defects:
 * "florida state" really is two institutions, and "purdue" returning the main campus over Purdue
 * Global is correct even though the probe asked for Global. A human triages the output, and only
 * the real defects go into tests/search_gold_set.json, which IS a gate.
 *
 * Usage: make search-probe   (requires site/value-check/data/schools.json)
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const TW = require(path.join(ROOT, "site/assets/college-search.js"));
const file = path.join(ROOT, "site/value-check/data/schools.json");
if (!fs.existsSync(file)) {
  console.log("no schools.json; run the site build first");
  process.exit(0);
}
const data = JSON.parse(fs.readFileSync(file, "utf8")).schools;
const MIN_ENROLMENT = 12000; // big enough that someone is likely to type its short name

/* The shapes people actually use: the name without its campus suffix, the name without its
   institution word, "X at Y" said as "X Y", and "University of X" said as "X university". */
function forms(name) {
  const out = new Set();
  const base = name.replace(/^The\s+/i, "");
  out.add(base.replace(/-Main Campus$/i, ""));
  out.add(base.replace(/\s+(University|College|Institute of Technology)\b.*$/i, "").trim());
  const at = base.match(/^(.*?)\s+at\s+(.*)$/i);
  if (at) out.add(at[1].replace(/^University of\s+/i, "") + " " + at[2]);
  const dash = base.match(/^(.*?)-(.*)$/);
  if (dash) out.add(dash[1].replace(/^University of\s+/i, "") + " " + dash[2]);
  if (/^University of /i.test(base)) out.add(base.replace(/^University of\s+/i, "") + " university");
  return [...out].map((s) => s.trim().toLowerCase()).filter((s) => s.length > 3);
}

const big = data.filter((s) => (s.enrollment || 0) > MIN_ENROLMENT);
const fails = [];
let asked = 0;
for (const s of big) {
  for (const q of forms(s.name)) {
    asked++;
    const hits = TW.searchSchools(data, q);
    const top = hits[0] && hits[0].name;
    if (top !== s.name) fails.push({ q, want: s.name, got: top || "(nothing)", n: s.enrollment });
  }
}
fails.sort((a, b) => b.n - a.n);
const seen = new Set();
const uniq = fails.filter((f) => !seen.has(f.q) && seen.add(f.q));

console.log(`search probe: ${big.length} institutions, ${asked} colloquial forms`);
console.log(`candidates for triage: ${uniq.length}\n`);
for (const f of uniq) {
  console.log(`  "${f.q}"`);
  console.log(`      expected: ${f.want}`);
  console.log(`      returned: ${f.got}`);
}
console.log("\nTriage these by hand. Real defects belong in tests/search_gold_set.json.");
