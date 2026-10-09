# FVT/GE reporting-list monitor: the contract (for review, not built)

Draft, 9 October 2026. Nothing here is implemented or scheduled. It states what a monitor for ED's
FVT/GE reporting list would check, what it may conclude, and what it must never do, so the
contract can be reviewed before any code exists.

## Why, and what is known

ED re-publishes the "List of Institutions That Previously Submitted FVT/GE Data" on
fsapartners.ed.gov (11 August, 28 August, 25 September and 8 October 2026), and says it will keep
doing so "through Jan. 15, 2027". The finding is built from one registered version at a time. The
monthly FVT Monitor watches the College Scorecard only, so the list's three updates went unnoticed
until a manual check on 8 October.

From a GitHub runner (run 37858847524, commit `d85b6ad`, 8 October): the announcement page answered
a GET with 200, and the October spreadsheet a HEAD with 200. **A GET of a spreadsheet from a runner
has not been tested.** The monitor's first job is to establish that, and its absence is a failure,
not a pass.

## What it watches

- The announcement page (GENERAL-26-49), currently
  `.../ge-data-reporting-stats-early-implementation-and-next-steps-publication-updated-oct-8-2026`.
  ED changes this URL when it updates the page; the monitor must follow ED's redirect or report the
  page as moved, never fall back to an old copy.
- Every spreadsheet the page links (`/sites/default/files/YYYY-MM/*.xlsx`).
- The registry of releases Truewise has accepted: `RELEASES` in `pipeline/build_fvtge_source.py`
  (compile date, publication date, URL, SHA-256, columns, statuses). The monitor reads it; it never
  edits it.

## The states it can report

Exactly one per run. Only state 3 may be described as unchanged.

| # | State | When | Exit | Issue |
|---|---|---|---|---|
| 1 | **Could not check** | The page GET fails: transport error, timeout, or a non-2xx after redirects | fail | open or update |
| 2 | **Page not understood** | The page loads but no spreadsheet links are found, or its structure is not recognised | fail | open or update |
| 3 | **Verified unchanged** | Every linked spreadsheet is registered, AND the newest registered one, re-downloaded by GET, matches its registered SHA-256 | pass | close if open |
| 4 | **New version** | A linked spreadsheet is not in the registry, and its download is a valid workbook (checks below) | fail (attention) | open or update, with the report |
| 5 | **Registered file changed** | A registered URL now returns different bytes | fail (attention) | open or update |
| 6 | **Download not usable** | A GET returns 2xx but the body is not a valid workbook (HTML, truncated, wrong type) | fail | open or update |

A run that finds several conditions reports the most serious, in the order 1, 2, 6, 5, 4, and lists
the rest. "No issue open" does not by itself mean healthy: health is state 3 within the staleness
window below.

## Checks on every downloaded spreadsheet

Recorded in the run's report whatever the outcome: method, URL, final URL after redirects, HTTP
status, content type, byte length, SHA-256, and any error.

1. The body is a zip (`PK\x03\x04`) and opens with openpyxl; the sheets Overview, Technical (where
   ED provides it), Variable Definitions, Frequencies and Data are present.
2. ED's compile date, read from its own text ("compiled on October 5th, 2026"), and its update line
   ("UPDATE 10/8/2026").
3. The Data header, compared with every registered layout; a new or reordered column is reported by
   name.
4. Status vocabulary: every value in every component column, compared with the registered
   statuses; any new status is listed with its count. Nothing is mapped onto an old meaning.
5. Identifiers: rows, distinct OPEIDs, OPEIDs not six characters, rows with values but no OPEID.
6. ED's derived counts and flags against the components, and the Frequencies sheet against the rows,
   both ways (the same rules as the parser, run in report mode).
7. For a new version only, a comparison with the newest registered release: rows listed, added and
   removed by OPEID; the 2024 and 2025 count and, where present, the 2026 count, each with its own
   denominator. These are reported as what the file says, never as findings.

## What it must never do

- Report a source it could not fetch, or a file it could not open, as unchanged (states 1, 2 and 6).
- Treat a successful HEAD as a successful download.
- Commit, push, change `published/`, `site/`, the registry or the finding. Permissions:
  `contents: read`, `issues: write`.
- Retry under a different identity or impersonate a browser. It sends the project's own agent; a
  refusal is the answer.
- Close a "new version" issue itself, except when a later run reaches state 3, which requires that
  a human has registered the release.

## Schedule and staleness

- Weekly until 15 January 2027 (ED's stated end of updates), then monthly; plus manual dispatch.
- Each run reports the days since the last state 3. Over 14 days, the run says so and opens or
  updates the issue, so a monitor that has been failing quietly, or not running, is visible.
- Downloads: one page and normally one spreadsheet (about 0.5 MB) a run.

## When a new version arrives (human steps, never automated)

1. Download it locally; read ED's Overview and Technical notes in full.
2. Register it in `RELEASES` (SHA-256, compile and publication dates, columns, statuses) and run the
   parser, which refuses anything it does not recognise.
3. Update the finding through the normal path: prototype if the layout or meaning changed, then a PR
   with the gate, layout check, an `/updates/` entry and review.

## Tests, before it is scheduled

No network in CI: recorded HTTP responses as fixtures, one for each state (a known page; a page with
a new link; 403; a timeout; HTML served as `.xlsx`; a truncated zip; changed bytes under a registered
URL; a workbook with a new status; a page with no links). Each must produce its state, exit code and
issue action. The first scheduled run is then watched by hand.

## Open questions for review

1. Weekly, or more often near ED's update dates?
2. After 15 January 2027: monthly, or stop until ED announces the next cycle?
3. Should the 2026-cycle count in a new version be reported alongside the 2024 and 2025 count, or only
   the structural checks?
4. One issue for both monitors, or separate issues (recommended: separate, since the sources fail
   independently)?
