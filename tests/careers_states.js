// Careers renders unknown values in words in its list, links each row to that major and degree's own
// page, and forwards the old ?field= addresses there.
//
// This runs the page's own script in jsdom with fields.json stubbed. No field in today's data is
// missing a count, a range or a share, so a page built from real data cannot show these states; the
// fixture can. The view a major used to open in on this page is gone (November 2026): each major and
// degree has a static page, whose own unknown states are tested in tests/test_major_degree_pages.py.
//
// Usage: node tests/careers_states.js   (no built site needed: the fields are a fixture)
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const html = fs.readFileSync("site/careers/index.html", "utf8");
const inline = Array.from(html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)).map((m) => m[1]);
const app = inline.reduce((a, b) => (b.length > a.length ? b : a));
const page = html.replace(/<script[\s\S]*?<\/script>/g, "");

const field = (over) => ({
  cip: "5138", cip2: "51", family: "Health", name: "Registered Nursing", cred: "3",
  credential: "Bachelor's Degree", cred_short: "Bachelor's", med: 80000, p25: 70000, p75: 90000,
  programs: 12, schools: 10, pass_pct: 92, page: "/majors/registered-nursing/bachelors/", ...over,
});
const FIXTURE = {
  fields: [
    field({ schools: null }),
    field({ cred: "2", credential: "Associate's Degree", cred_short: "Associate's", programs: null, p25: null, pass_pct: null, page: "/majors/registered-nursing/associates/" }),
    field({ cip: "5139", name: "Practical Nursing", programs: null, schools: null, page: "/majors/practical-nursing/bachelors/" }),
  ],
};

let failures = 0;
const check = (ok, msg) => {
  console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`);
  if (!ok) failures += 1;
};
const settle = () => new Promise((r) => setTimeout(r, 30));

async function render(search) {
  // jsdom does not navigate: it reports each attempt, which is how a forward is seen here.
  const virtualConsole = new VirtualConsole();
  let navigations = 0;
  virtualConsole.on("jsdomError", (e) => { if (/navigation/i.test(String(e.message))) navigations += 1; });
  const dom = new JSDOM(page, { runScripts: "outside-only", url: "https://truewise.dev/careers/" + search, virtualConsole });
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
  return { d: w.document, w, errors, navigations: () => navigations };
}

const text = (el) => (el ? el.textContent.replace(/\s+/g, " ").trim() : "");

async function main() {
  // An old address forwards to the page that replaced the view.
  let { d, w, errors, navigations } = await render("?field=5138&cred=3");
  check(!errors.length, `an old address is handled without an error (${errors.join("; ") || "none"})`);
  check(navigations() === 1, `an old address navigates away once (attempts: ${navigations()})`);
  check(w.pageFor("5138", "3") === "/majors/registered-nursing/bachelors/", "a major and degree forwards to its own page");
  check(w.pageFor("5138", "2") === "/majors/registered-nursing/associates/", "the degree in the address decides the page");
  check(w.pageFor("5138", null) === "/majors/registered-nursing/", "a major with no degree forwards to the major's page");
  check(w.pageFor("5138", "9") === "/majors/registered-nursing/", "a degree with no page forwards to the major's page");
  check(w.pageFor("0000", "3") === null, "a field that is not in the data has no page");
  check(!/Major not found/.test(text(d.getElementById("app"))), "a known address never shows the not-found message");

  // A field that is not in the data says so and offers the list.
  ({ d, errors, navigations } = await render("?field=0000&cred=3"));
  check(!errors.length, "an unknown address is handled without an error");
  check(navigations() === 0, "an unknown address does not navigate");
  check(/Major not found/.test(text(d.getElementById("app"))), "an unknown address says the major was not found");
  check(d.querySelector("#app a.backlink[href='/careers/']") !== null, "and links back to the list");

  // Browse table.
  ({ d, errors, navigations } = await render(""));
  check(!errors.length, "browse view renders without an error");
  check(navigations() === 0, "the list does not navigate by itself");
  const links = Array.from(d.querySelectorAll(".cr-table a.mlink")).map((a) => a.getAttribute("href"));
  check(
    links.length === 3 && links.every((h) => /^\/majors\/[a-z0-9-]+\/[a-z0-9-]+\/$/.test(h)),
    `every row links to its major and degree page (${links.join(", ")})`
  );
  check(!/[?&]field=/.test(d.getElementById("app").innerHTML), "no row links to an old ?field= address");
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
