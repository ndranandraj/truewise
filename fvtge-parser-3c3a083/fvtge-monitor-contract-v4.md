# FVT/GE reporting-list monitor: the contract (for review, not built)

Version 4, 11 October 2026; three settings confirmed 4 November 2026 (Decisions recorded, below).
Earlier versions: `fvtge-monitor-contract-v1.md`, `-v2.md`, `-v3.md` (beside this file locally; in
`fvtge-parser-3c1097f/` on the review branch).

- Version 2 added the preliminary review's six requirements: unchanged needs both sources,
  concurrent observations are kept, separate clocks, an independent check for silence, source status
  kept apart from publication status, and explicit incident handling.
- Version 3 recorded Anand's answers to the four open questions, thresholds that match the cadence,
  and a watchdog outside GitHub's schedules.
- Version 4 makes the 11 October review's three amendments, and records Anand's choice of
  Healthchecks.io as the watchdog:
  1. Three signals are kept apart: the run completed, the source checks succeeded, and a release
     awaits human review. A completed run proves execution whatever the source said. A pending
     review is never an execution failure, and restored access recovers a transport incident while a
     review is still pending.
  2. State 1 covers any failed required request: the page, the registered workbook, or a candidate
     workbook.
  3. Cadence transitions have rules: what decides the mode, what ends review mode, and how the first
     deadline after a change is set without hiding a real gap.

Nothing here is implemented or scheduled. It states what a monitor for ED's FVT/GE reporting list
would check, what it may conclude, and what it must never do, so the contract can be reviewed
before any code exists.

## Why, and what is known

ED re-publishes the "List of Institutions That Previously Submitted FVT/GE Data" on
fsapartners.ed.gov (11 August, 28 August, 25 September and 8 October 2026), and says it will keep
doing so "through Jan. 15, 2027". The finding is built from one registered version at a time. The
monthly FVT Monitor watches the College Scorecard only, so the list's three updates went unnoticed
until a manual check on 8 October. These dates are what was known on 11 October 2026; ED's page was
not rechecked for this document on 4 November.

From a GitHub runner (run 37858847524, commit `d85b6ad`, 8 October): the announcement page answered
a GET with 200, and the October spreadsheet a HEAD with 200. **A GET of a spreadsheet from a runner,
and a check that what comes back is a valid workbook, have not been tested.** That path and every
fixture state must be exercised before the monitor is scheduled. A HEAD success and a download on
Anand's Mac (or the reviewer's) are not substitutes.

## What it watches

- **The announcement page** (GENERAL-26-49), currently
  `.../ge-data-reporting-stats-early-implementation-and-next-steps-publication-updated-oct-8-2026`.
  ED changes this URL when it updates the page. The monitor follows ED's redirects and records the
  final URL; if the page has moved without a redirect, that is state 1 or 2, never a fall back to an
  old copy.
- **Every spreadsheet the page links** (`/sites/default/files/YYYY-MM/*.xlsx`).
- **The registry** of releases Truewise has accepted: `RELEASES` in `pipeline/build_fvtge_source.py`
  **as it is on `main`** (compile date, publication date, URL, SHA-256, columns, statuses, frequency
  groups). Read, never edited. A release on a branch, in an open PR or in a local commit is not
  registered.
- **The version the live finding uses**: the `compiled` value in `published/fvtge_reporting.parquet`
  on `main`. Read, never edited.

## Three signals, never merged

Every run reports three things separately. None of them stands in for another.

| Signal | Question | Values | Watched by |
|---|---|---|---|
| **Execution** | Did the checker run to the end and save its report? | completed, or not completed | Healthchecks.io (outside GitHub), plus the run history |
| **Source checks** | Did every required request succeed, with usable content? | succeeded; failed (which request, why); unavailable (not attempted, why) | the check-failure issue and its threshold |
| **Review** | Is a release waiting for a person? | none; new version pending; changed file pending; registered but not yet published | the new-version and changed-file issues, review reminders |

**A completed run** is one that reached its last step, wrote a report with every required field
(each required request recorded as succeeded or failed, each state observed, the clocks), and
uploaded that report as a workflow artifact. Only then is the heartbeat pinged.

- A run that reports a source failure (states 1, 2, 6) is a **completed** run. It proves the
  monitor executed; it does not prove the source is healthy.
- A run that reports a new version (state 4) or a changed file (state 5) is a **completed** run. It
  proves execution without claiming the source is unchanged.
- A crash, an unexpected exception, a cancelled or timed-out job, or a report that could not be
  saved or uploaded is **not** a completed run, even if a partial report survives. A partial report
  is kept as evidence and labelled incomplete. No ping is sent.
- The checker's exit code reflects execution only: 0 for a completed run whatever the source said,
  non-zero for a run that did not complete. Source and review outcomes travel in the report and the
  issues, so a red workflow run always means the monitor itself failed.
- A pending review produces **review reminders**, labelled as such, on the review issue. It never
  produces an execution failure, a missed heartbeat or a check-failure issue.

## The states

### Verified unchanged needs both sources

State 3 is the only state that may be described as unchanged, and it needs **all** of:

1. **The page is understood.** The GET completes with 2xx on fsapartners.ed.gov after redirects; the
   page is recognised (it names GENERAL-26-49 and the list's title); and its spreadsheet links are
   extracted, at least one of them.
2. **The page shows no unreviewed release.** Every linked spreadsheet is in the registry on `main`.
   A link that is not, even an older one, is a new observation, not a pass.
3. **The newest registered file is intact.** Its GET completes with 2xx, the body is a valid workbook
   (the checks below), and its SHA-256 matches the registry.

A successful re-download of the old registered file does not, by itself, show that the page has no
new version, and an understood page does not show that the registered file is still the one ED
serves. Each of 1 to 3 is required.

### The requests a run makes

A run makes these requests, each independent of the others: a failure of one never skips another,
so every observation that can be made is made.

1. The page GET.
2. The GET of the newest registered workbook, at its registered URL. It is made even when the page
   GET fails, because its URL comes from the registry, not the page.
3. One GET for each linked spreadsheet that is not in the registry (a candidate). These need the page.

Older registered workbooks are not re-downloaded on each run. The report says so; it does not claim
their bytes were checked.

### The states, and how concurrent observations are kept

| # | State | When | Source checks | Review | Issue class |
|---|---|---|---|---|---|
| 1 | **Could not check** | **Any required request fails**: the page GET, the registered workbook GET, or a candidate workbook GET (transport error, timeout, or a non-2xx after redirects). The report names each failed request, its URL and the error. | failed | (unchanged) | check failure |
| 2 | **Page not understood** | The page loads but is not recognised, or no spreadsheet links are found | failed | (unchanged) | check failure |
| 3 | **Verified unchanged** | All three requirements above | succeeded | none from this run | (none) |
| 4 | **New version** | A linked spreadsheet is not in the registry on `main` | as its requests went | new version pending | new version |
| 5 | **Registered file changed** | A registered URL now returns different bytes | succeeded for that request | changed file pending | changed file |
| 6 | **Download not usable** | A GET returns 2xx but the body is not a valid workbook (HTML, truncated, wrong type) | failed | (unchanged) | check failure |

A run records **every** observation, not only one. If a new link appears while a registered file
has changed or failed to download, the report and the issues carry both. The order 1, 2, 6, 5, 4
decides only the run's headline; it never removes an observation from the report, and it never sets
the exit code (above).

Combinations that must each be reported in full:

- A new link whose download fails (403, timeout): state 4 (a new link exists) and state 1 (the
  candidate request failed). The new version's counts are **unavailable: download failed**.
- A new link whose download is not a workbook: states 4 and 6. Counts unavailable, with the reason.
- The page fails but the registered workbook downloads intact: state 1 for the page request; the
  registered file's checksum result is still reported. State 3 is impossible.
- The page is understood but the registered workbook request fails: state 1 for that request; any new
  link is still state 4. State 3 is impossible.

## Checks on every downloaded spreadsheet

Recorded in the run's report whatever the outcome: method, URL, final URL after redirects, HTTP
status, content type, byte length, SHA-256, and any error.

1. The body is a zip (`PK\x03\x04`) and opens with openpyxl, from the same bytes that were hashed;
   the sheets Overview, Technical (where ED provides it), Variable Definitions, Frequencies and Data
   are present.
2. ED's compile date, read from its own text ("compiled on October 5th, 2026"), and its update line
   ("UPDATE 10/8/2026").
3. The Data header, compared with every registered layout; a new or reordered column is reported by
   name.
4. Status vocabulary: every value in every component column, compared with the registered
   statuses; any new status is listed with its count. Nothing is mapped onto an old meaning.
5. Identifiers: rows, distinct OPEIDs, OPEIDs that are not six digits as text, rows with values but
   no OPEID.
6. ED's derived counts and flags against the components, and the Frequencies sheet against the rows,
   both ways, with the parser's rules run in report mode: the release's counted groups exactly (none
   missing, none unexpected), each outcome listed once, identifier rows and notes the only other
   rows.
7. For a new version only, a comparison with the newest registered release: rows listed, added and
   removed by OPEID; the 2024 and 2025 count and, where present, the 2026 count, each with its own
   denominator. These are reported as what the file says, never as findings.

## The clocks

Every run reports each separately, and none is reset to hide a gap:

- **Last completed run**: the execution clock. It drives the heartbeat, and the run history lists
  every expected run that did not complete.
- **Last successful source check**: the last completed run in which every required request
  succeeded and every downloaded file was usable (no state 1, 2 or 6). A pending review does not stop
  this clock: a run that reports a valid new version every day is a successful source check every
  day. The staleness rule uses this clock, with the threshold of the mode in force (below). Over the
  threshold, the run opens or updates a check-failure issue.
- **Last verified unchanged**: the last state 3. Reported, not alerted on: while a review is pending
  it cannot advance, and that is a review matter, not a failure.
- **Failed attempts**: each failed request's time, URL and error, listed separately. A failure never
  moves the last-success time.
- **Review pending since**: when the oldest unregistered release was first seen, and when it was
  last seen on ED's page.
- **Source age**: ED's compile date of the newest registered release, and separately ED's compile
  date of the newest release seen on the page. A recent check of an old source is still an old
  source.
- **Time since human review**: when the newest registered release reached the registry on `main`.

The clocks are carried from run to run in each completed run's report (a workflow artifact, kept
90 days). If the previous report cannot be read, the run says the history is **unavailable**, shows
each clock as unknown rather than zero or now, and treats a check as due.

## Who notices if it goes silent

A monitor cannot report its own non-execution, and another GitHub schedule is not independent of it:
GitHub can disable scheduled workflows in a public repository after 60 days without activity, and
can delay or drop scheduled runs, so a second schedule fails the same way at the same time.

**Healthchecks.io, on Anand's account (decided 11 October 2026).** One check per monitor, so one
source can never mask the other's silence:

| Check | Pinged by | Period | Grace | Alert after the last completed run |
|---|---|---|---|---|
| FVT/GE monitor | each completed daily run (below) | 1 day | 1 day | 2 days: one dropped run is tolerated, two are not |
| Scorecard monitor | each completed monthly run (the 8th) | 31 days | 14 days | 45 days |

- **The alert delay is period plus grace, set on purpose.** The totals in the last column are the
  policy; the two settings are chosen to add up to them. No grace is added on top of a policy figure.
- **The FVT/GE check does not change when the cadence does.** The workflow runs every day in every
  mode; on a day when no source check is due it makes no request to ED, records that decision, and
  still completes. So the external check always expects a daily ping, and the cadence (weekly,
  daily, monthly) governs only the source checks, whose thresholds are enforced by the monitor's own
  report and check-failure issue. A 45-day policy therefore cannot become 45 days plus grace: no
  45-day period is configured outside the monitor. (The alternative, a Healthchecks period that
  follows the cadence, would need the check reconfigured at every transition, by hand or with an
  account API key held in CI. That is more fragile and puts a broader credential in GitHub.)
- **What a ping carries:** nothing but the request itself. No body, no data, no results, no report
  contents, no repository access. It is sent only by a completed run on `main`, after the report
  artifact has uploaded.
- **The ping URLs are credentials.** They live only in GitHub Actions secrets (`HC_PING_FVTGE`,
  `HC_PING_SCORECARD`), are passed to the ping step through the environment, and never appear in the
  repository, a workflow file, a log, an issue, a report or chat. Anand creates the checks and the
  secrets; nobody else needs the URLs.
- **Notifications:** email to Anand, confirmed by a test notification before anything is scheduled.
- A run that does not complete sends no success ping. A failure step may also send Healthchecks'
  explicit fail signal so a crash alerts at once; that is optional, and relied on only after it has
  been tested. Lateness alone is enough to catch a crash.
- **Inside GitHub, as a second signal only:** every completed run lists the expected runs since the
  last one that did not complete. It is not relied on to notice that no run happened.

## Source status and publication status are different

The report states three versions and never merges them:

1. **Latest ED release seen** on the page (compile and publication date).
2. **Latest registered release** in `RELEASES` on `main`.
3. **Version the live finding uses** (`published/fvtge_reporting.parquet`, `compiled`).

State 3 means 1 equals 2 and the file is intact. It does not mean the live article has been
refreshed: when 2 is newer than 3, the report says the finding is behind the registered data.

## Incidents

- **One open issue per class** (check failure, new version, changed file), each updated on later
  runs rather than duplicated. A comment is added only when the observations change, except for
  labelled review reminders (below).
- **Evidence is kept**: each run's JSON report and the downloaded file's checksum (not the file)
  as a workflow artifact, retained 90 days, linked from the issue.
- **Check-failure issues** are about source checks only. The monitor closes one when a later
  completed run has a successful source check: every required request succeeded with usable content.
  That does **not** need state 3. Restored access recovers the incident even while a new version
  still awaits registration; the pending review stays open on its own issue.
- **New-version and changed-file issues** are closed only by a person. A later run only comments:
  that the release has reached the registry on `main` (with the commit), or that the link is no longer
  on ED's page. An unchanged response must not erase unresolved review work.
- **Review reminders**: while a review is pending, a comment headed "Review reminder" is added to its
  issue once a week (decided 4 November 2026), giving the release, when it was first
  seen, and the three versions above. A reminder is never labelled or counted as a failure.
- **A reopened observation**: if a person closes a new-version issue while that link is still on ED's
  page and still unregistered on `main`, the next run that sees it reopens the issue and says why.

## What it must never do

- Report a source it could not fetch, or a file it could not open, as unchanged (states 1, 2, 6).
- Treat a successful HEAD as a successful download.
- Count an incomplete run as a completed one, or ping the heartbeat from one.
- Ping the heartbeat, or open, comment on or close an issue, from a run that is not on `main`. A run
  dispatched on another branch is a trial: it reports only, and says so.
- Treat a pending review as an execution or source failure, or keep a check-failure issue open
  because a review is pending.
- Commit, push, change `published/`, `site/`, the registry or the finding. Permissions:
  `contents: read`, `issues: write`, `actions: read` (to read the previous run's report).
- Retry under a different identity or impersonate a browser. It sends the project's own agent; a
  refusal is the answer.
- Close a new-version or changed-file issue.

## Schedule and cadence

These are Truewise's monitoring policy, not ED's publication schedule: ED says only that it will
"periodically update and share this list through Jan. 15, 2027". Dates are UTC.

The workflow runs once a day (plus manual dispatch). Each run first decides the **mode in force**,
then whether a source check is due under it. An attempted source check is a completed run that made
its requests, whatever they returned: a failed weekly check is tried again a week later, not the next
day, so two failed weekly checks in a row reach the 14-day threshold. Manual dispatch on `main` always
checks.

| Mode | When | Source check due | Silence threshold (last successful source check) |
|---|---|---|---|
| Weekly | to 31 December 2026 | 7 days after the last attempted source check | 14 days |
| Daily (deadline window) | 1 to 31 January 2027 | every day | each due check that fails is reported; an issue once 2 days pass without a successful source check |
| Daily (review) | while a review is pending (below), whatever the date | every day | as daily |
| Monthly | from 1 February 2027 | 30 days after the last attempted source check | 45 days |

### Which mode is in force

1. **Review mode overrides every date-based mode**, monthly included. It is in force while either
   holds: a release seen on ED's page is not in the registry on `main`, or a new-version or
   changed-file issue is open.
2. Otherwise the date decides: weekly, daily (January) or monthly.

### Transitions

- **A later fetch failure does not end review mode or change the cadence.** If the page cannot be
  fetched, the pending release cannot be confirmed as still linked, but it is still unregistered, and
  its issue is still open. Absence of evidence resolves nothing.
- **Review mode ends only on the authoritative branch.** Registration counts when the release (its
  URL and SHA-256 as downloaded) is in `RELEASES` on `main`, and only from the first run that reads
  it there. A local commit, a pushed branch or an open PR does not end it. The other exit is a person
  closing the issue after ED has withdrawn the link (the run's comment shows it gone); if the link is
  still there and unregistered, the issue is reopened.
- **Every transition sets its first expected check and its first deadline**, recorded in the report
  with the time the mode changed:
  - *Tightening* (weekly to daily, monthly to daily): the first daily check is due on the first run
    in the new mode, and the deadline is the earlier of the old mode's deadline (last successful
    source check plus 14 or 45 days) and the transition time plus 2 days. A 6-day-old weekly check
    is not called a missed daily check before any daily check was due; a 13-day-old one still breaches
    on its original 14-day deadline, a day later, because a transition never moves an existing
    deadline later.
  - *Loosening* (daily to weekly, daily to monthly): the new threshold runs from the last successful
    source check, never from the transition, so a gap is not extended by the change.
  - A transition never closes an open check-failure issue. Only a successful source check does.
- **Historical clocks are kept.** A transition changes which threshold applies, not what the clocks
  say: the report always shows the real time since the last successful source check, the last
  verified unchanged and the last completed run.

The cadence is reviewed if ED announces a new reporting cycle or a replacement source. Downloads: one
page and normally one spreadsheet (about 0.5 MB) on a day a check is due; none on other days.

## What a new version's report contains (decided)

When the downloaded candidate passes every check above, the report gives **both reporting
populations separately**: for the 2024 and 2025 cycles, and for the 2026 cycle (or any later cycle
the file adds), each with its own count, denominator, number of components and ED's compile date.
They are never added together or set side by side as one measure. If the layout is unknown, the
download failed, or any check fails, the counts are reported as **unavailable**, with the reason,
never inferred.

## Issues (decided)

Separate issues for the Scorecard monitor and the FVT/GE monitor, since their sources fail
independently. Within each source, one open issue per incident class, as above. A recovery in one
source never closes an incident in the other. New-version and changed-file issues are closed only by
a person.

## When a new version arrives (human steps, never automated)

1. Download it locally; read ED's Overview and Technical notes in full.
2. Register it in `RELEASES` (SHA-256, compile and publication dates, columns, statuses, frequency
   groups) and run the parser, which refuses anything it does not recognise.
3. Merge the registration to `main`. Review mode ends at the first monitor run after that merge.
4. Update the finding through the normal path: prototype if the layout or meaning changed, then a PR
   with the gate, layout check, an `/updates/` entry and review.

## Tests, before it is scheduled

No network in CI: recorded HTTP responses as fixtures. Each fixture must produce its state or states,
its three signals, the issue actions, the exit code, the ping decision and every clock.

**Sources and content:**

- A known page; a page with a new link; a new link plus a changed registered file.
- Transport failures: page 403; page timeout; **registered workbook 403**; **registered workbook
  timeout**; **candidate workbook 403**; **candidate workbook timeout**; page failure with the
  registered workbook intact.
- Malformed content: a new link whose download is HTML; HTML served as `.xlsx`; a truncated zip;
  changed bytes under a registered URL; a workbook with a new status; a workbook with a missing,
  unexpected or duplicated frequency group; a page with no links; a moved page without redirect.

**Signals and incidents:**

- A crash part-way through: not completed, no ping, non-zero exit, partial report labelled incomplete.
- A report that cannot be uploaded: not completed, no ping.
- A valid new version on several daily runs: each completed, each pinged, each a successful source
  check; no check-failure issue; one new-version issue with weekly reminders.
- Restored access while a review is pending: the check-failure issue closes, the new-version issue
  stays open.
- A run dispatched on a branch: reports only, no ping, no issue changes.
- Previous report unavailable: clocks unknown, check due.

**Cadence:**

- Weekly to daily with the last successful check 6 days old: no missed check reported; deadline at the
  transition plus 2 days.
- Weekly to daily with it 13 days old: the original 14-day deadline holds.
- Daily to monthly: the deadline is the last successful check plus 45 days, not the transition plus
  45 days.
- Review mode in February: daily, not monthly.
- A fetch failure during review: still review mode, still daily, issue still open.
- Registration on a branch only: still review mode. Registration merged to `main`: review mode ends
  on the next run.

**Before any schedule, on the real services:**

1. One manual run from a runner exercises the real page GET, the real workbook GET and the workbook
   checks on what comes back.
2. A heartbeat delivery test: a completed manual run on `main` pings, and Healthchecks.io shows the
   ping.
3. A deliberate missed-ping alert: a temporary test check with a short period and grace is left
   unpinged, and the email arrives. The temporary check is then deleted. The real checks' period and
   grace are then read back from the dashboard and recorded (without their URLs).
4. A weekly-to-daily transition run, from recorded history, confirming the first deadline.

## Decisions recorded

9 October 2026, Anand:

1. Weekly, or more often near ED's update dates? **Weekly normally; daily from 1 to 31 January 2027,
   and while a newly announced update is under review.**
2. After 15 January 2027: monthly, or stop? **Continue monthly from February.**
3. Report the 2026-cycle count in a new version? **Yes: both cycles separately, with validated counts
   and their own denominators; unavailable if validation fails.**
4. One issue or separate? **Separate issues for Scorecard and FVT/GE.**

Plus: the silence threshold is 45 days in monthly mode (14 weekly, daily as above), and the watchdog
must be outside GitHub's schedules.

11 October 2026, Anand: **Healthchecks.io, on Anand's account, with separate checks for Scorecard and
FVT/GE**; alert delay set deliberately as period plus grace; ping URLs only in GitHub Actions
secrets.

4 November 2026, Anand:

1. How does the FVT/GE check follow the cadence? **It does not: the workflow runs daily in every mode,
   with a fixed Healthchecks check of 1 day plus 1 day of grace (alert 2 days after the last completed
   run).** The cadence governs only the source checks, and a day with no check due makes no request
   to ED.
2. The Scorecard check? **31 days plus 14 days of grace (alert 45 days after the last completed run).**
3. Review reminders? **Weekly, labelled as review reminders on the review issue.**

## Still open

- **The monitor depends on draft PR #17.** It reads `RELEASES` on `main`, and on 4 November 2026 that
  exists only on the `fvtge-parser` branch: `main`'s parser has no registry. The monitor cannot be
  scheduled until #17 has merged.
- **PR #21 (unmerged) adds `pipeline/source_freshness.py`,** a check a person runs (`make freshness`)
  that reads the same announcement page and compares workbook file names with the one the site uses.
  It downloads nothing, so it does not check a registered file's bytes or a new file's contents, and
  it has no schedule or watchdog. It does not replace this monitor. Whether the two should share their
  page-reading code is open.
- Creating the two checks, the email integration and the two secrets: Anand's account.
- A GET of a spreadsheet from a GitHub runner, and the workbook check on what it returns, are still
  untested. Neither the schedule nor the heartbeat is set up until that run, every fixture above and
  the four real-service tests have passed.
