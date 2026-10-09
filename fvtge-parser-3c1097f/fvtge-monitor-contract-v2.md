# FVT/GE reporting-list monitor: the contract (for review, not built)

Version 2, 9 October 2026. Version 1 (same day) is kept beside this file as
`fvtge-monitor-contract-v1.md`. Version 2 adds the six requirements from the preliminary review of
9 October: unchanged needs both sources, concurrent observations are kept, three separate clocks,
an independent check for silence, source status kept apart from publication status, and explicit
incident handling.

Nothing here is implemented or scheduled. It states what a monitor for ED's FVT/GE reporting list
would check, what it may conclude, and what it must never do, so the contract can be reviewed
before any code exists.

## Why, and what is known

ED re-publishes the "List of Institutions That Previously Submitted FVT/GE Data" on
fsapartners.ed.gov (11 August, 28 August, 25 September and 8 October 2026), and says it will keep
doing so "through Jan. 15, 2027". The finding is built from one registered version at a time. The
monthly FVT Monitor watches the College Scorecard only, so the list's three updates went unnoticed
until a manual check on 8 October.

From a GitHub runner (run 37858847524, commit `d85b6ad`, 8 October): the announcement page answered
a GET with 200, and the October spreadsheet a HEAD with 200. **A GET of a spreadsheet from a runner,
and a check that what comes back is a valid workbook, have not been tested.** That path and every
fixture failure state must be exercised before the monitor is scheduled. A HEAD success and a
download on Anand's Mac are not substitutes.

## What it watches

- **The announcement page** (GENERAL-26-49), currently
  `.../ge-data-reporting-stats-early-implementation-and-next-steps-publication-updated-oct-8-2026`.
  ED changes this URL when it updates the page. The monitor follows ED's redirects and records the
  final URL; if the page has moved without a redirect, that is state 1 or 2, never a fall back to an
  old copy.
- **Every spreadsheet the page links** (`/sites/default/files/YYYY-MM/*.xlsx`).
- **The registry** of releases Truewise has accepted: `RELEASES` in `pipeline/build_fvtge_source.py`
  (compile date, publication date, URL, SHA-256, columns, statuses). Read, never edited.
- **The version the live finding uses**: the `compiled` value in `published/fvtge_reporting.parquet`
  on `main`. Read, never edited.

## The states

### Verified unchanged needs both sources

State 3 is the only state that may be described as unchanged, and it needs **all** of:

1. **The page is understood.** The GET completes with 2xx on fsapartners.ed.gov after redirects; the
   page is recognised (it names GENERAL-26-49 and the list's title); and its spreadsheet links are
   extracted, at least one of them.
2. **The page shows no unreviewed release.** Every linked spreadsheet is in the registry. A link that
   is not, even an older one, is a new observation, not a pass.
3. **The newest registered file is intact.** Its GET completes with 2xx, the body is a valid workbook
   (the checks below), and its SHA-256 matches the registry.

A successful re-download of the old registered file does not, by itself, show that the page has no
new version, and an understood page does not show that the registered file is still the one ED
serves. Each of 1 to 3 is required.

### The states, and how concurrent observations are kept

| # | State | When | Exit | Issue class |
|---|---|---|---|---|
| 1 | **Could not check** | The page GET fails: transport error, timeout, or a non-2xx after redirects | fail | check failure |
| 2 | **Page not understood** | The page loads but is not recognised, or no spreadsheet links are found | fail | check failure |
| 3 | **Verified unchanged** | All three requirements above | pass | (none) |
| 4 | **New version** | A linked spreadsheet is not in the registry | fail (attention) | new version |
| 5 | **Registered file changed** | A registered URL now returns different bytes | fail (attention) | changed file |
| 6 | **Download not usable** | A GET returns 2xx but the body is not a valid workbook (HTML, truncated, wrong type) | fail | check failure |

A run records **every** observation, not only one. If a new link appears while a registered file
has changed or failed to download, the report and the issues carry both. The order 1, 2, 6, 5, 4
decides only the run's headline and exit code; it never removes an observation from the report.
A new link whose download is not usable is reported as both state 4 (a new link exists) and state 6
(it could not be read).

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
5. Identifiers: rows, distinct OPEIDs, OPEIDs that are not six digits as text, rows with values but
   no OPEID.
6. ED's derived counts and flags against the components, and the Frequencies sheet against the rows,
   both ways (the parser's rules, run in report mode).
7. For a new version only, a comparison with the newest registered release: rows listed, added and
   removed by OPEID; the 2024 and 2025 count and, where present, the 2026 count, each with its own
   denominator. These are reported as what the file says, never as findings.

## Three clocks, kept apart

Every run reports each separately:

- **Last fully successful check**: the time of the last state 3. The staleness rule uses this, and
  only this: over 14 days, the run says so and opens or updates a check-failure issue.
- **Failed attempts**: each failed run's time and state, listed separately. A failure never moves
  the last-success time.
- **Source age**: ED's compile date of the newest registered release, and separately ED's compile
  date of the newest release seen on the page. A recent check of an old source is still an old
  source.
- **Time since human review**: when the newest registered release was registered.

## Who notices if it goes silent

A monitor cannot report its own non-execution. So:

- An **independent check** reads the FVT/GE monitor's last-success record (the last workflow run
  that ended in state 3, through the GitHub API) and opens an issue when it is over 14 days old or
  absent. Proposed host: the existing monthly FVT Monitor, which already runs on its own schedule,
  plus a weekly lightweight workflow so a gap is caught within the same 14-day window.
- **The schedule fits the rule**: weekly runs, so two consecutive missed or failed weeks trip the
  14-day threshold, not one transient failure.
- GitHub disables scheduled workflows in a repository after 60 days without activity. The
  independent check, and this document, must say so; a disabled schedule is silence, not health.

## Source status and publication status are different

The report states three versions and never merges them:

1. **Latest ED release seen** on the page (compile and publication date).
2. **Latest registered release** in `RELEASES`.
3. **Version the live finding uses** (`published/fvtge_reporting.parquet`, `compiled`).

State 3 means 1 equals 2 and the file is intact. It does not mean the live article has been
refreshed: when 2 is newer than 3, the report says the finding is behind the registered data.

## Incidents

- **One open issue per class** (check failure, new version, changed file), each updated on later
  runs rather than duplicated. A comment is added only when the observations change.
- **Evidence is kept**: each run's JSON report and the downloaded file's checksum (not the file)
  as a workflow artifact, retained 90 days, linked from the issue.
- **Closure.** The monitor may close a check-failure issue when a later run reaches state 3. It
  never closes a new-version or changed-file issue: those are closed by a person once the release is
  registered (or the change explained), and a later state 3 run only comments on them. An unchanged
  response must not erase unresolved review work.

## What it must never do

- Report a source it could not fetch, or a file it could not open, as unchanged (states 1, 2, 6).
- Treat a successful HEAD as a successful download.
- Commit, push, change `published/`, `site/`, the registry or the finding. Permissions:
  `contents: read`, `issues: write`.
- Retry under a different identity or impersonate a browser. It sends the project's own agent; a
  refusal is the answer.
- Close a new-version or changed-file issue.

## Schedule

- Weekly until 15 January 2027 (ED's stated end of updates), then as decided below; plus manual
  dispatch.
- Downloads: one page and normally one spreadsheet (about 0.5 MB) a run.

## When a new version arrives (human steps, never automated)

1. Download it locally; read ED's Overview and Technical notes in full.
2. Register it in `RELEASES` (SHA-256, compile and publication dates, columns, statuses) and run the
   parser, which refuses anything it does not recognise.
3. Update the finding through the normal path: prototype if the layout or meaning changed, then a PR
   with the gate, layout check, an `/updates/` entry and review.

## Tests, before it is scheduled

No network in CI: recorded HTTP responses as fixtures, one for each state and for the combinations
above (a known page; a page with a new link; a new link plus a changed registered file; a new link
whose download is HTML; 403; a timeout; HTML served as `.xlsx`; a truncated zip; changed bytes under a
registered URL; a workbook with a new status; a page with no links; a moved page without redirect).
Each must produce its state or states, exit code, issue class and action, and the three clocks.
Then one manual run from a runner exercises the real GET and workbook check, before any schedule.

## Open questions for review

1. Weekly, or more often near ED's update dates?
2. After 15 January 2027: monthly, or stop until ED announces the next cycle?
3. Should the 2026-cycle count in a new version be reported alongside the 2024 and 2025 count, or only
   the structural checks?
4. One issue for both monitors, or separate issues (recommended: separate, since the sources fail
   independently)?
