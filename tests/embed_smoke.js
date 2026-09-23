// Functional smoke test for the embeddable value-check widget in site/embed/index.html.
// Runs the page's real JS in a minimal DOM stub against the generated schools.json and asserts the
// card renders the right verdict, rate, and backlink. Usage: node tests/embed_smoke.js
const fs = require("fs");

const html = fs.readFileSync("site/embed/index.html", "utf8");
// Largest inline block, not the first one on the page. Taking the first is a trap that has now been
// sprung once: adding a two-line script above the application on /compare/ made its smoke test
// evaluate the wrong code and then fail with an error about the application, which had not changed.
// search_smoke.js already selected by size; compare_smoke.js and this file did not, so the lesson
// had been learned in one place and left in the other two.
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g))
  .map((m) => m[1]);
if (!inline.length) throw new Error("site/embed/index.html has no inline script to run");
const js = inline.reduce((a, b) => (b.length > a.length ? b : a));
if (!/function card/.test(js)) {
  throw new Error("the largest inline script is not the embed widget; refusing to assert against it");
}
const schools = JSON.parse(fs.readFileSync("site/value-check/data/schools.json", "utf8")).schools;

let fails = 0;
const ck = (name, cond) => { console.log((cond ? "PASS  " : "FAIL  ") + name); if (!cond) fails++; };

// Run the widget's script once with a given ?school value, return the rendered app HTML.
async function render(search) {
  const app = { innerHTML: "" };
  global.document = { getElementById: (id) => (id === "app" ? app : { textContent: "" }) };
  let replacedTo = null;
  global.location = { search, replace: (u) => { replacedTo = u; } };
  global.fetch = async () => ({ json: async () => ({ schools }) });
  global.URLSearchParams = URLSearchParams;
  global.navigator = {};
  eval(js);
  await new Promise((r) => setTimeout(r, 0)); // let the async IIFE settle
  render.replacedTo = replacedTo;
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

  // No param: the how-to moved to /about/embed/, in the shared site design. The widget sends
  // visitors there rather than drawing its own docs.
  await render("");
  ck("no-param view sends visitors to the how-to page", render.replacedTo === "/about/embed/");
  const docs = fs.readFileSync("site/about/embed/index.html", "utf8");
  ck("the how-to carries a copyable snippet that works as it is",
    docs.includes("&lt;iframe") && docs.includes("/embed/?school=223232"));
  ck("the how-to uses the shared stylesheet", docs.includes('href="/styles.css'));

  console.log(fails ? "\n" + fails + " FAILURE(S)" : "\nALL EMBED CHECKS PASSED");
  process.exit(fails ? 1 : 0);
})();
