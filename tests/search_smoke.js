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
// The alias map + matcher now live in the shared module both pickers load.
const TWSearch = require("../site/assets/college-search.js");

// Wrap the region in a function so its declarations stay local (SCHOOLS + esc + TWSearch are
// injected), then return the functions under test.
const factory = eval(
  "(function (SCHOOLS, esc, TWSearch) {\n" + region + "\nreturn { searchSchools, detectState, emptyStateHTML };\n})",
);
const { searchSchools, detectState, emptyStateHTML } = factory(SCHOOLS, esc, TWSearch);

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

/* The match reason has to survive the whole path to the reader, not merely be computed.
 *
 * The provider set why:"close spelling" correctly and the Value Check page never showed it: the
 * compatibility shim mapped results to r.raw and dropped everything else, so a correct value died
 * one function short of the screen. "The matcher produces it" was the wrong thing to have trusted,
 * and these check the two remaining links in the chain: the shim carries it, and the card renders it
 * as text rather than as a colour or a badge. */
const withWhy = (q) => searchSchools(q).map((s) => s.why);
ck(
  '"massachusets institute" carries why="close spelling" through the shim',
  withWhy("massachusets institute")[0] === "close spelling",
);
ck(
  '"ucla" carries why="alias" through the shim',
  withWhy("ucla")[0] === "alias",
);
ck(
  'a plain name match carries no reason, so the card stays quiet when there is nothing to explain',
  withWhy("baylor university")[0] === undefined,
);
// And the shim must not write onto the shared school objects: a reason from one search stuck to a
// school would then appear in every later one.
searchSchools("massachusets institute");
ck(
  "the shim copies rather than tagging the shared data",
  SCHOOLS.every((s) => s.why === undefined),
);
// The renderer must put it in the card, as real text.
const page = fs.readFileSync("site/value-check/index.html", "utf8");
ck("the result card renders the reason", /s\.why \?/.test(page) && /class="why"/.test(page));

// State detection powers the routed empty state.
ck('detectState("zzqq texas") === TX', detectState("zzqq texas") === "TX");
ck('detectState("something ohio") === OH', detectState("something ohio") === "OH");
ck('detectState("nonsense") === null', detectState("nonsense") === null);
const eh = emptyStateHTML("zzqq texas");
ck("empty state links the Texas index + best-value list", eh.includes("/colleges/tx/") && eh.includes("best-value-colleges-tx"));

console.log(fails ? "\n" + fails + " FAILURE(S)" : "\nALL SEARCH CHECKS PASSED");
process.exit(fails ? 1 : 0);
