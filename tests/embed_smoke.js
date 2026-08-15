// Functional smoke test for the embeddable value-check widget in site/embed/index.html.
// Runs the page's real JS in a minimal DOM stub against the generated schools.json and asserts the
// card renders the right verdict, rate, and backlink. Usage: node tests/embed_smoke.js
const fs = require("fs");

const html = fs.readFileSync("site/embed/index.html", "utf8");
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const schools = JSON.parse(fs.readFileSync("site/value-check/data/schools.json", "utf8")).schools;

let fails = 0;
const ck = (name, cond) => { console.log((cond ? "PASS  " : "FAIL  ") + name); if (!cond) fails++; };

// Run the widget's script once with a given ?school value, return the rendered app HTML.
async function render(search) {
  const app = { innerHTML: "" };
  global.document = { getElementById: (id) => (id === "app" ? app : { textContent: "" }) };
  global.location = { search };
  global.fetch = async () => ({ json: async () => ({ schools }) });
  global.URLSearchParams = URLSearchParams;
  global.navigator = {};
  eval(js);
  await new Promise((r) => setTimeout(r, 0)); // let the async IIFE settle
  return app.innerHTML;
}

(async () => {
  // Baylor University (unitid 223232): 62 pass, 2 fail.
  const bay = await render("?school=223232");
  ck("renders the school name", bay.includes("Baylor University"));
  ck("shows the pass/fail verdict (62 of 64 ... 2 fall short)", /62<\/b> of <b>64<\/b>/.test(bay) && bay.includes("fall short"));
  ck("shows the clear-the-bar rate (97% of 64)", bay.includes("97%") && bay.includes("clear the bar"));
  ck("backlinks to the pre-rendered college page", bay.includes('href="https://truewise.dev/college/baylor-university/"'));
  ck("carries attribution to truewise.dev", bay.includes("truewise.dev"));
  ck("credits the federal source", bay.includes("College Scorecard"));

  // Unknown id: graceful message, no crash.
  const missing = await render("?school=000000");
  ck("unknown id shows a graceful fallback", missing.includes("No college found"));

  // No param: the docs/snippet view with a copy-paste iframe.
  const docs = await render("");
  ck("no-param view shows the embed docs", docs.includes("Embed a college's value check"));
  ck("docs include a copy-paste iframe snippet", docs.includes("&lt;iframe") && docs.includes("/embed/?school="));

  console.log(fails ? "\n" + fails + " FAILURE(S)" : "\nALL EMBED CHECKS PASSED");
  process.exit(fails ? 1 : 0);
})();
