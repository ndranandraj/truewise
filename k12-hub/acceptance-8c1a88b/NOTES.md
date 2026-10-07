# PR #14 checks on 8c1a88b

Revision: `8c1a88b` on `k12-hub`, two commits after `14f0c92`:
- `5f08096` FVT/GE finding: the key figure's "of 4,635 colleges" may wrap inside its box. **Outside
  #14's pages**, fixed here at Anand's choice because the new check below found it.
- `8c1a88b` High Schools lookup: result names stay inside their cards; no match is said in the status
  region; course cards size their columns in em; result names are h2; the layout check's new
  boxed-text probe and populated-search route; `tests/k12_lookup_states.js`.

Built with `./preview-build.sh` and served from `site/` on localhost:8787, 6 October 2026
(America/Los_Angeles). The runs used the working tree that was then committed as `5f08096` and
`8c1a88b`; between the runs and the commits only the build's stylesheet stamps were removed, as the
repository requires. Browsers: Playwright Firefox 155.0 and Chromium 153.0.8010.12; axe-core
4.13.0. "200% text" is Firefox's native text-only zoom, body text confirmed at 30px.

The earlier folder, `acceptance-14f0c92/`, is unchanged and stays as the record for that revision.

## Files

| File | What it is |
|---|---|
| `gate-output.txt` | `./scripts/gate.sh`: GATE PASSED, including the new `k12_lookup_states` |
| `layout-check-output.txt` | `node tests/layout_check.js`: 92 of 92 page-states, 0 blocking (adds the `k12-search` route, and the boxed-text probe in the enlarged pass) |
| `accept.js`, `accept-output.txt` | The acceptance script and its output: 90 passed, 0 failed |
| `accept-changes.diff` | Exactly what changed in `accept.js` since the `14f0c92` folder |
| `axe14.js`, `axe-output.txt` | The accessibility scan: 12 states, all loaded and clean |
| `axe-changes.diff` | Exactly what changed in `axe14.js` since the `14f0c92` folder |
| `acceptance-pr14.md` | The acceptance record, updated with the review of `14f0c92` and these fixes |

## The 90 acceptance checks

`accept.js` is the version recreated on 5 October (see `acceptance-14f0c92/NOTES.md`), extended. Its
76 checks there were 48 layout states plus 14 interaction checks in each of Firefox and Chromium.
Additions since, all shown in `accept-changes.diff`:

**Layout: 48, unchanged.** Three pages at eight sizes, normal and 200% text, in Firefox.

**Populated search: 8, new.** `?q=international` at 320, 390, 768 and 1280px, normal and 200% text,
in Firefox. Each requires HTTP 200, body text at the expected size, at least one result card, no text
in any card past the card's border (the defect that review found: the document-width check passed
while "INTERNATIONAL" ran past its card), and no page wider than the screen.

**Per browser: 17, up from 14** (34 in all, from 28):
- the 14 from before, with one widened: the keyboard order now continues through **both** tiles,
  State report cards and Compare schools (it stopped after the first; the check's count is the same,
  its coverage is larger);
- 3 new: "zzqxv" puts "No high schools match "zzqxv"." in the status region and nothing in the list;
  a new query replaces it with the count; clearing the field clears it.

48 + 8 + 34 = 90.

## The accessibility scan

Each state must now return HTTP 200 and show its intended content (the expected heading, result
cards, or the no-match message) before it is scanned; a state that does not load is recorded as a
failure, not a clean scan. Two states were added: a populated search (`?q=international`) and no
match (`?q=zzqxv`). 6 states at 390 and 1280px: 12 scans.

The populated search first failed: result names were `h3` directly under the page's `h1` (axe
heading-order; live has it too). They are `h2` now, which **changes their size at normal text from
16.8px to 18px** (`--t-sub`, the token the hub's tool cards use), since this page's heading sizes
must use type tokens. After that, all 12 scans are clean.

## Outstanding

- Safari (macOS and iOS): not tested.
- Real device: not tested.
- VoiceOver: not tested; script in `acceptance-pr14.md`.
- Timing on a quiet machine: not rerun for #14 (the earlier run is inconclusive, not a pass).
