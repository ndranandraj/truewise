// Careers renders unknown values in words, in both the browse table and a major's detail view.
//
// This runs the page's own script in jsdom with fields.json stubbed. No field in today's data is
// missing a count, a range or a share, so a page built from real data cannot show these states; the
// fixture can. Before this check, a missing school count crashed the detail view on
// .toLocaleString() instead of saying "not reported".
//
// Usage: node tests/careers_states.js   (no built site needed: the fields are a fixture)
const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync("site/careers/index.html", "utf8");
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)).map((m) => m[1]);
const app = inline.reduce((a, b) => (b.length > a.length ? b : a));
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");

const field = (over) => ({
  cip: "5138", cip2: "51", family: "Health", name: "Registered Nursing", cred: "3",
  credential: "Bachelor's Degree", cred_short: "Bachelor's", med: 80000, p25: 70000, p75: 90000,
  programs: 12, schools: 10, pass_pct: 92, ...over,
});
const FIXTURE = {
  fields: [
    field({ schools: null }),
    field({ cred: "2", credential: "Associate's Degree", cred_short: "Associate's", programs: null, p25: null, pass_pct: null }),
    field({ cip: "5139", name: "Practical Nursing", programs: null, schools: null }),
  ],
};

let failures = 0;
const check = (ok, msg) => {
  console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`);
  if (!ok) failures += 1;
};
const settle = () => new Promise((r) => setTimeout(r, 30));

async function render(search) {
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/careers/" + search });
  const w = dom.window;
  const errors = [];
  w.addEventListener("error", (e) => errors.push(String(e.message)));
  w.addEventListener("unhandledrejection", (e) => errors.push(String(e.reason)));
  w.fetch = async (url) =>
    String(url).includes("fields.json")
      ? { ok: true, status: 200, json: async () => FIXTURE }
      : { ok: false, status: 404, json: async () => ({}) };
  w.scrollTo = () => {};
  w.eval(app);
  await settle();
  return { d: w.document, errors };
}

const text = (el) => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");

async function main() {
  // Detail view, school count missing.
  let { d, errors } = await render("?field=5138&cred=3");
  check(!errors.length, `detail view renders without an error (${errors.join("; ") || "none"})`);
  check(text(d.querySelector("h1")) === "Registered Nursing", "detail view shows the major");
  check(
    text(d.querySelector(".cr-count")) === "Based on 12 programs reporting this degree; the number of schools is not reported.",
    `missing school count is named (got: "${text(d.querySelector(".cr-count"))}")`
  );
  const schoolCells = Array.from(d.querySelectorAll('td[data-label="Schools"]')).map(text);
  check(schoolCells.includes("not reported"), "the degree table's missing school count reads not reported");

  // Detail view, program count, range and share all missing.
  ({ d, errors } = await render("?field=5138&cred=2"));
  check(!errors.length, "detail view with several unknowns renders without an error");
  check(/the number of programs is not reported/.test(text(d.querySelector(".cr-count"))), "missing program count is named");
  check(/not assessed/.test(text(d.querySelector(".headline"))), "missing range and share read not assessed");

  // Detail view, both counts missing.
  ({ d, errors } = await render("?field=5139&cred=3"));
  check(
    text(d.querySelector(".cr-count")) === "The number of programs and schools behind these figures is not reported.",
    "both counts missing are named together"
  );

  // Browse table.
  ({ d, errors } = await render(""));
  check(!errors.length, "browse view renders without an error");
  const body = text(d.querySelector(".cr-table tbody"));
  check(/not reported/.test(body), "browse table's missing school count reads not reported");
  check(/not assessed/.test(body), "browse table's missing range and share read not assessed");
  check(!/insufficient data|n\/a|\bNaN\b|undefined/.test(text(d.getElementById("app"))), "no old or broken placeholders anywhere");

  if (failures) {
    console.error(`\n${failures} Careers state check(s) failed`);
    process.exit(1);
  }
  console.log("\nCareers unknown-value states hold");
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
