# PR #14 checks on 14f0c92 (refreshed onto main)

Revision: `14f0c92`, the PR branch `k12-hub` (`d6054e9`) with `main` at `6058655` merged in
(`main` includes PR #15). Built with `./preview-build.sh` and served from `site/` on
localhost:8787. Run 5 October 2026 (America/Los_Angeles). These are #14's own results; PR #16's
acceptance does not count for #14.

Browsers: Playwright Firefox 155.0 and Chromium 153.0.8010.12; axe-core 4.13.0. "200% text" is
Firefox's native text-only zoom (`ui.textScaleFactor` 200, `browser.display.os-zoom-behavior` 2),
with body text confirmed at 30px; no CSS substitute.

## Files

| File | What it is |
|---|---|
| `gate-output.txt` | `./scripts/gate.sh`: GATE PASSED |
| `layout-check-output.txt` | `node tests/layout_check.js`: 88 of 88 page-states, 0 blocking (includes the `k12-school` route) |
| `accept.js`, `accept-output.txt` | The acceptance script and its output: 76 passed, 0 failed |
| `axe14.js`, `axe-output.txt` | axe-core scan: no violations in 8 states |
| `acceptance-pr14.md` | The acceptance record and the VoiceOver script (written for `d6054e9`; still applies) |

## How `accept.js` came to exist, and what it covers

The original acceptance script lived in a session scratchpad, which was cleared when the Mac
restarted. `accept.js` here was **recreated on 5 October** from the checklist in
`acceptance-pr14.md` and from the final version of the original as recorded in the working
session. The original file is gone, so the two cannot be compared byte for byte. One known
difference: the recreation exits with a failure code when a check fails; the original only
printed the count. A matching total (76 of 76 on `d6054e9`, 76 of 76 here) does not by itself show
the same coverage, so the coverage is listed in full:

**Layout: 48 checks.** Three pages (the hub `/k12/`, the lookup `/k12/advanced-courses/`, and Lane
Technical's school page) at eight sizes (320×568, 320×700, 375×667, 390×844, 768×1024, 1100×800,
1280×800, 1440×900), each at normal size and 200% text, in Firefox. Each check requires all of:
body text at the expected size (15px, or at least 28px at 200%), no page wider than the screen,
nothing in the hub's search form past the form's edges, and the Search button's text not clipped.

**Per browser, Firefox then Chromium: 14 checks each, 28 in all.**
1. Enter in the hub's search goes to `/k12/advanced-courses/?q=Lane+Tech`, the lookup's field reads
   "Lane Tech" and has focus, and Lane Technical High School is the first result.
2. The Search button hands off the same way (Stuyvesant High School found).
3. An empty search lands on the lookup without an error.
4. A two-letter search asks for at least three letters.
5. to 9. Each of the five example links opens its own school page, with the expected name and no
   "School not found" or "No data for this school".
10. "Find another school" returns to the search.
11. Focus is visible (an outline of at least 2px) on the field, the button, the examples and the
    tiles.
12. Tab order after the section links: the field, Search, the five examples, then the tiles.
13. Enter on a focused example opens it.
14. Back returns to the hub.

48 + 28 = 76.

**Not in `accept.js`:** the accessibility scan (`axe14.js`, run separately), the gate and the layout
check (their own outputs above).

## Outstanding

- Safari (macOS and iOS): not tested.
- Real device: not tested.
- VoiceOver: not tested; script in `acceptance-pr14.md`.
- Timing on a quiet machine: not rerun for #14. The earlier run was on a loaded machine and is
  inconclusive, not a pass.
