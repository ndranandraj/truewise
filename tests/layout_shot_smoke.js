// The layout check's screenshot retry, with a fake page instead of a browser.
//
// A full-page screenshot that timed out used to throw out of the layout check's loop and end the run
// with nothing reported. Now it is retried once, and a second failure becomes an advisory finding.
// This forces each path: success, one failure then success, and two failures.
//
// Usage: node tests/layout_shot_smoke.js
const { makeShot } = require("./layout_shot.js");

let failures = 0;
const check = (ok, msg) => {
  console.log(`${ok ? "ok  " : "FAIL"}  ${msg}`);
  if (!ok) failures += 1;
};

// A page whose first `failCount` screenshots throw a Playwright-style timeout.
function fakePage(failCount) {
  const calls = [];
  return {
    calls,
    async screenshot(opts) {
      calls.push(opts);
      if (calls.length <= failCount) {
        throw new Error("page.screenshot: Timeout 30000ms exceeded.\nCall log: ...");
      }
    },
  };
}

async function main() {
  const logs = [];
  const shot = makeShot("/tmp/layout-check-test", (m) => logs.push(m));

  let page = fakePage(0);
  let findings = [];
  await shot(page, "home-390.png", findings);
  check(page.calls.length === 1 && !findings.length && !logs.length, "a screenshot that works is taken once, with no finding");
  check(page.calls[0].path.endsWith("/screenshots/home-390.png") && page.calls[0].fullPage === true, "it is a full-page capture in screenshots/");

  page = fakePage(1);
  findings = [];
  await shot(page, "home-desktop.png", findings);
  check(page.calls.length === 2 && !findings.length, "one failure is retried and the retry's capture is kept, with no finding");
  check(logs.length === 1 && /retrying screenshot home-desktop\.png after: Error: page\.screenshot: Timeout/.test(logs[0]), "the retry is logged with the first line of the error");

  page = fakePage(2);
  findings = [];
  let threw = null;
  try {
    await shot(page, "profile-1280.png", findings);
  } catch (e) {
    threw = e;
  }
  check(!threw, "two failures do not throw, so the run carries on to the next route");
  check(page.calls.length === 2, "it gives up after one retry, not more");
  check(findings.length === 1 && findings[0].kind === "screenshot-failed", "two failures become one screenshot-failed finding");
  check(findings[0] && findings[0].blocking === false, "the finding is advisory: the page was still measured");
  check(findings[0] && findings[0].detail === "No screenshot profile-1280.png: Error: page.screenshot: Timeout 30000ms exceeded.", "the finding names the file and the first line of the error");

  if (failures) {
    console.error(`\n${failures} screenshot retry check(s) failed`);
    process.exit(1);
  }
  console.log("\nScreenshot retry holds");
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
