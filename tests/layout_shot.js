// Screenshots for the layout check, kept apart from it so the retry can be tested without a browser.
//
// A screenshot is evidence for the reader of the report, not a measurement. A full-page capture of a
// tall page can time out on its own, and an unguarded one threw out of the loop and ended the run.
// One retry, as for page loads; a second failure is an advisory finding, never a crash.
const path = require("path");

function makeShot(outDir, log = console.log) {
  return async function shot(page, file, findings) {
    const opts = { path: path.join(outDir, "screenshots", file), fullPage: true };
    try {
      await page.screenshot(opts);
    } catch (first) {
      log(`  retrying screenshot ${file} after: ${String(first).split("\n")[0]}`);
      try {
        await page.screenshot(opts);
      } catch (e) {
        findings.push({ kind: "screenshot-failed", blocking: false,
          detail: `No screenshot ${file}: ${String(e).split("\n")[0]}` });
      }
    }
  };
}

module.exports = { makeShot };
