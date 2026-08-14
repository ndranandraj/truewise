// Functional smoke test for the college search in site/value-check/index.html.
// Extracts the SHIPPED search logic (alias map, ranking, state detection, empty state) and
// runs it against the real generated schools.json, asserting the queries that used to fail.
// Usage: node tests/search_smoke.js   (requires site/value-check/data/schools.json to exist)
const fs = require("fs");

const html = fs.readFileSync("site/value-check/index.html", "utf8");
const bigScript = html.match(/<script>([\s\S]*?)<\/script>/g).sort((a, b) => b.length - a.length)[0];
const js = bigScript.replace(/^<script>/, "").replace(/<\/script>$/, "");
// Pull just the pure matching region (no DOM), between the two section banners.
const region = js.slice(
  js.indexOf("// ---- Search matching"),
  js.indexOf("// ---- Search view ----"),
);

const SCHOOLS = JSON.parse(fs.readFileSync("site/value-check/data/schools.json", "utf8")).schools;
const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// Wrap the region in a function so its declarations stay local (SCHOOLS + esc are injected),
// then return the functions under test.
const factory = eval(
  "(function (SCHOOLS, esc) {\n" + region + "\nreturn { searchSchools, detectState, emptyStateHTML };\n})",
);
const { searchSchools, detectState, emptyStateHTML } = factory(SCHOOLS, esc);

let fails = 0;
const ck = (name, cond) => {
  console.log((cond ? "PASS  " : "FAIL  ") + name);
  if (!cond) fails++;
};
const top = (q) => {
  const h = searchSchools(q);
  return h[0] ? h[0].name : "(none)";
};

// The exact queries the audit caught failing on the old substring-only search.
ck('"texas austin" -> UT Austin', top("texas austin").includes("Texas at Austin"));
ck('"ut austin" -> UT Austin', top("ut austin").includes("Texas at Austin"));
ck('"univ of texas austin" -> UT Austin', top("univ of texas austin").includes("Texas at Austin"));
ck('"baylor" -> Baylor University (size tiebreak beats College of Medicine)', top("baylor") === "Baylor University");
ck('"ucla" -> University of California-Los Angeles', top("ucla").includes("California-Los Angeles"));
ck('"uc berkeley" -> University of California-Berkeley', top("uc berkeley").includes("California-Berkeley"));
ck('"usc" -> University of Southern California', top("usc") === "University of Southern California");
ck('"nyu" -> New York University', top("nyu") === "New York University");
ck('"mit" -> Massachusetts Institute of Technology', top("mit") === "Massachusetts Institute of Technology");

// State detection powers the routed empty state.
ck('detectState("zzqq texas") === TX', detectState("zzqq texas") === "TX");
ck('detectState("something ohio") === OH', detectState("something ohio") === "OH");
ck('detectState("nonsense") === null', detectState("nonsense") === null);
const eh = emptyStateHTML("zzqq texas");
ck("empty state links the Texas index + best-value list", eh.includes("/colleges/tx/") && eh.includes("best-value-colleges-tx"));

console.log(fails ? "\n" + fails + " FAILURE(S)" : "\nALL SEARCH CHECKS PASSED");
process.exit(fails ? 1 : 0);
