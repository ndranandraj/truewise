// Behavioural smoke for the Stage 4.2 canonical-profile progressive enhancement (profile.js +
// table.js onMore). Under jsdom. Folded into `make test-components`.
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const dom = new JSDOM(`<!doctype html><body>
  <div data-tw-profile data-tail="programs-tail.json" data-remaining="2">
    <script type="application/json" class="tw-profile-data">
      {"rows":[
        {"program":"Computer Science","credential":"Master's","earnings":195622,"premium":161809,"verdict":"pass","debt":20500,"payback":0.1,"completers":2416},
        {"program":"Nursing","credential":"Bachelor's","earnings":70000,"premium":36000,"verdict":"pass","horizon":"1yr_after_completion","debt":22000,"payback":0.6,"completers":300}
      ],"coverage":{"measured":184,"total":489},"baseline":36498,"caption":"Programs"}
    </script>
    <div class="tw-profile-static"><p>server-rendered fallback table</p></div>
  </div>
</body>`);
const { window } = dom;
global.window = window;
global.document = window.document;
window.__TW_PROFILE_NO_AUTO = true; // drive enhancement manually

const load = (rel) => new window.Function(fs.readFileSync(path.join(__dirname, "..", rel), "utf8")).call(window);
load("components/table.js");
load("components/profile.js");

let pass = 0;
const fail = [];
const check = (c, m) => (c ? pass++ : fail.push(m));

const root = document.querySelector("[data-tw-profile]");

// Injected fetch returns the 2 tail programs; asserts the right URL was requested.
let requested = null;
const fakeFetch = async (url) => {
  requested = url;
  return {
    programs: [
      { program: "Philosophy", credential: "Bachelor's", earnings: null, premium: null, verdict: "insufficient", debt: null, payback: null, completers: 41 },
      { program: "History", credential: "Bachelor's", earnings: 44000, premium: 8000, verdict: "pass", horizon: "1yr_after_completion", debt: 19000, payback: 2.4, completers: 60 },
    ],
  };
};

window.TWProfile.enhance(root, { fetch: fakeFetch, base: "https://truewise.dev/college/x/" });

// 1. Static fallback replaced by the interactive table with coverage + 2 static rows.
const mount = root.querySelector(".tw-profile-static");
check(mount.querySelector("table.tw-table") !== null, "static table was not upgraded");
check(/184 of 489/.test(mount.textContent), "coverage not rendered from the JSON island");
check(mount.querySelectorAll("tbody .tw-tr").length === 2, "expected the 2 static rows before loading");

// 1b. The static 1-year row (Nursing) carries the marker after enhancement (island -> table.js).
check(mount.querySelectorAll(".tw-oneyr").length === 1, "static 1-year row lost its marker after enhancement");

// 2. The "Show all N" control reflects the true total (static + remaining).
const showAll = mount.querySelector(".tw-showall");
check(showAll && /Show all 4 programs/.test(showAll.textContent), "show-all count wrong (2 static + 2 tail)");

// 3. Loading the tail fetches the right URL, appends, and announces.
showAll.click();
setTimeout(() => {
  check(requested === "https://truewise.dev/college/x/programs-tail.json", `wrong tail URL: ${requested}`);
  const rows = mount.querySelectorAll("tbody .tw-tr");
  check(rows.length === 4, `expected 4 rows after loading tail, got ${rows.length}`);
  check(mount.querySelector(".tw-showall") === null, "show-all should be gone after loading");
  check(/All 4 programs shown/.test(mount.textContent), "load completion not announced");

  // 3b. The 1-year marker is preserved through enhancement for BOTH the static row and the tail row
  // (Nursing static + History tail), so a 1-year program loaded as tail row is labelled like row 1.
  check(mount.querySelectorAll(".tw-oneyr").length === 2, "tail 1-year row should also be labelled after load");

  // 4. Sorting now covers the full set, insufficient sinks to the bottom.
  const earningsBtn = [...mount.querySelectorAll(".tw-th__sort")].find((b) => /earnings/i.test(b.textContent));
  earningsBtn.click();
  const order = [...mount.querySelectorAll("tbody .tw-td--program")].map((t) => t.textContent);
  check(order[0] === "Computer Science", "highest earner should sort first over the full set");
  check(order[order.length - 1] === "Philosophy", "insufficient row should sink to the bottom");

  console.log(`profile smoke (canonical progressive enhancement): ${pass}/${pass + fail.length} passed`);
  if (fail.length) {
    fail.forEach((f) => console.log("  FAIL: " + f));
    process.exit(1);
  }
  console.log("ALL PROFILE CHECKS PASSED");
}, 10);
