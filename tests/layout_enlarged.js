// The layout check's enlarged-text pass, kept apart from it so its failure paths can be tested with a
// fake page (tests/layout_enlarged_smoke.js), as the screenshot retry is.
//
// Each route is loaded fresh at each enlarged width, text is doubled, and the probes judge the result.
// A pass that did not establish the page it meant to measure is a failure, never a clean result: an
// earlier version reloaded with errors swallowed and no status check, and headerProbe() returned no
// findings when the header was absent, so a failed load could report clean (October 2026 review).

/** Widths for the enlarged-text pass. 769px is the narrowest desktop table layout, where the Careers
 *  degree table overflowed its section with doubled text; 390 and 1280 are the phone and laptop. */
const ENLARGED_WIDTHS = [
  { label: "390", width: 390, height: 844, mobile: true },
  { label: "769", width: 769, height: 900, mobile: false },
  { label: "1280", width: 1280, height: 900, mobile: false },
];

const first = (e) => String(e).split("\n")[0];

/**
 * Load `url` in `page`, require the header (and any route-specific `ready` selectors) to render,
 * double the text, then run each probe in the page. Returns the findings; every failure to reach
 * the state being measured is itself a blocking finding.
 */
async function enlargedPass(page, url, { probes, ready = [], doubleText, timeout = 30000, readyTimeout = 10000, settle = 300 }) {
  let resp;
  try {
    resp = await page.goto(url, { waitUntil: "load", timeout });
  } catch (e) {
    return [{ kind: "enlarged-load-failed", blocking: true, detail: `${url} did not load for the enlarged-text pass: ${first(e)}` }];
  }
  if (!resp || resp.status() >= 400) {
    return [{ kind: "enlarged-load-failed", blocking: true, detail: `${url} returned ${resp ? resp.status() : "no response"}, so nothing was measured at enlarged text.` }];
  }
  for (const sel of [".site-header", ...[].concat(ready)]) {
    try {
      await page.waitForSelector(sel, { timeout: readyTimeout });
    } catch (e) {
      return [{ kind: "enlarged-not-ready", blocking: true, detail: `${url}: ${sel} never rendered, so the enlarged-text pass measured nothing (${first(e)}).` }];
    }
  }
  await page.evaluate(doubleText);
  await page.waitForTimeout(settle);
  const findings = [];
  for (const probe of probes) {
    const got = await page.evaluate(probe);
    findings.push(...((got && got.findings) || []));
  }
  return findings;
}

module.exports = { ENLARGED_WIDTHS, enlargedPass };
