# Truewise — Iteration Plan & Checklist

_Written 2026-07-06. Execution companion to `Truewise - Project Plan v2 (Reputation-First).md`.
Every iteration follows the same cycle: **Design → Code → Test → Implement (deploy)**, and
ends with a **Verify gate**: the deployed tool must demonstrably work before the next
iteration starts. Nothing is "done" until it is live and verified._

**Standing rules for every iteration**

- [ ] Work happens on a branch; merge to `main` only when tests pass in CI.
- [ ] Every merge to `main` auto-deploys the static site (Cloudflare Pages).
- [ ] Update the impact log with anything shippable, citable, or screenshotable.
- [ ] Never silently impute suppressed/missing values; render "insufficient data."

---

## Iteration 0 — Foundation & first deploy (~1–1.5 days)

**Goal:** public repo, CI, and a live placeholder site. Proves the deploy pipeline before
any real code exists. Starts the 6-month JOSS clock.

**Use case, in plain terms:** there is no real product yet. A visitor typing truewise.us
sees a real, working page that says what Truewise is and what is coming. As the builder,
you can make a change on your laptop and watch it appear on the live site minutes later,
which proves the whole publishing machine works before anything important depends on it.

### Design
- [ ] Sketch repo layout: `pipeline/`, `site/`, `tests/`, `data/` (gitignored), `docs/`.
- [ ] Choose site framework: lightweight vanilla JS + Chart.js (per PLAN.md lean).
- [ ] Define CI stages: lint → pytest → build site → deploy.
- [ ] Write the one-page product brief (mission, modules, naming) as `docs/BRIEF.md`.

### Code
- [ ] Init repo, make it **public** (JOSS eligibility clock starts now).
- [ ] Add `requirements.txt`, linting (ruff), pytest scaffold, pre-commit hooks.
- [ ] GitHub Actions workflow: lint + test on PR; build + deploy on merge to `main`.
- [ ] Placeholder landing page (name, mission, "coming soon", methodology stub).

### Test
- [ ] CI runs green on a trivial PR (lint + one dummy test).
- [ ] Broken-test PR is correctly blocked (negative test of the gate).

### Implement / Deploy
- [ ] Connect repo to Cloudflare Pages; deploy the placeholder.
- [ ] Register truewise.us (manual step, US nexus attestation) and point DNS.
- [ ] Create the impact log (`docs/IMPACT_LOG.md` or private notes) with entry #1: repo public.

### ✅ Verify gate
- [ ] https://truewise.us loads over HTTPS from a clean browser/incognito.
- [ ] A test commit to `main` auto-deploys within minutes, visible live.
- [ ] Repo is publicly visible while `data/` stays untracked.

---

## Iteration 1 — Data spine v1: College Scorecard (~3–4 days)

**Goal:** Scorecard institution + field-of-study data lands in DuckDB/Parquet with
validation; dataset v0 published with a DOI.

**Use case, in plain terms:** the government publishes college data as thousands of messy
columns spread across giant files. After this iteration, a researcher, journalist, or
student of data science can download ONE clean, documented dataset from the site, open it,
and immediately ask questions like "what is the median earnings for nursing programs in
Texas" without spending days decoding federal files. It is not pretty yet; it is useful.

### Design
- [ ] Read the current Scorecard data dictionary; **confirm the earnings-premium field
      names** (HANDOFF.md open question #2, prerequisite for Value Check).
- [ ] Define the canonical schema: institution table (UnitID key), program table
      (UnitID + CIP + credential level), and the suppressed-value convention.
- [ ] Decide raw-file caching and refresh-versioning layout (`data/raw/YYYY-MM/`).
- [ ] Write the data dictionary for the published dataset (`docs/DATA_DICTIONARY.md`).

### Code
- [ ] Finish `pipeline/load_scorecard.py`: download bulk "Most Recent" files (resumable,
      checksummed), load into DuckDB, write partitioned Parquet.
- [ ] Identity layer: UnitID ↔ OPEID crosswalk table.
- [ ] Transform layer (SQL): typed columns, suppressed sentinels → NULL + flag column.
- [ ] Release script: package Parquet + data dictionary → GitHub Release; mint Zenodo DOI.

### Test
- [ ] Row-count sanity: ~6,000+ institutions; programs in expected range.
- [ ] Null/suppression rates within documented bounds per key column.
- [ ] Join test: UnitID joins institution ↔ program with zero orphans.
- [ ] Spot-check 5 known schools (e.g., a state flagship, a community college, a
      for-profit) against collegescorecard.ed.gov values.
- [ ] Schema-drift test fails loudly if ED renames columns.

### Implement / Deploy
- [ ] Publish dataset v0.1: GitHub Release + Zenodo DOI + Hugging Face dataset page.
- [ ] Add a "Data" page to the site linking dataset, dictionary, and DOI.

### ✅ Verify gate
- [ ] Fresh clone on a clean machine: `make data` (or documented commands) rebuilds the
      spine end-to-end without manual fixes.
- [ ] Download the published Parquet from the release link; open in DuckDB; run the 5-school
      spot-check successfully from ONLY the published artifact.
- [ ] Zenodo DOI resolves; HF page renders; impact log updated.

---

## Iteration 2 — FVT/GE monitor: mirror, archive, diff (~2–3 days)

**Goal:** dated snapshots of ED's live FVT transparency site data, diffed each refresh.
Time-critical: the site launched 2026-07-01 and figures may be revised.

**Use case, in plain terms:** the government just started publishing which college programs
leave graduates with too much debt or too little income, but it only shows today's numbers
and can quietly change them. After this iteration, anyone visiting the Monitor page can see
the headline ("X programs currently fail the earnings test"), and see what changed since
last month: which programs newly fail, which figures were revised, which rows disappeared.
A journalist can use this page as a source that the government itself does not provide.

### Design
- [ ] Inspect how the ED site serves data (bulk file, API, embedded JSON); pick the most
      stable extraction path; document it.
- [ ] Snapshot layout: `archive/fvt/YYYY-MM-DD/` raw + normalized table keyed on
      OPEID + program + credential.
- [ ] Diff spec: new failures, changed D/E or EP values, removed rows.

### Code
- [ ] Snapshot fetcher (polite, cached) + normalizer into the spine (join via OPEID).
- [ ] Diff engine producing a human-readable changelog per refresh.
- [ ] GitHub Actions monthly schedule for snapshot + diff.
- [ ] TAKE THE FIRST SNAPSHOT IMMEDIATELY (before anything else in this iteration).

### Test
- [ ] Normalizer handles the full national file without dropping rows (reconcile counts).
- [ ] Diff engine unit tests: synthetic added/changed/removed cases.
- [ ] Join coverage: % of FVT programs matched to Scorecard programs measured and documented.
- [ ] Cross-validation report: Scorecard EP fields vs ED site values; discrepancies listed.

### Implement / Deploy
- [ ] Commit first dated snapshot to the archive (this is artifact #1 of the monitor).
- [ ] "FVT/GE Monitor" page on the site: latest snapshot date, headline counts (programs
      failing D/E, failing EP), link to changelog.
- [ ] Scheduled action live and documented.

### ✅ Verify gate
- [ ] Monitor page live with real numbers; a manual second snapshot produces a correct
      (possibly empty) diff.
- [ ] Scheduled CI run completes on its own at least once.
- [ ] Spot-check 10 programs on the monitor page against ED's site directly.

---

## Iteration 3 — Value Check module (~4–5 days)

**Goal:** the flagship. Program-level lookup with plain-language warnings live on the site.

**Use case, in plain terms:** a high-school senior (or their parent) is considering a
specific program, say a certificate in medical assisting at a local for-profit college.
They search the school on Truewise, tap the program, and get a clear answer in one screen:
"Graduates of this program typically earn LESS than a high-school graduate in your state"
or "This program passes both federal value tests." No jargon, no 3,000-column spreadsheet,
just the honest number and where it came from. This is the moment Truewise becomes useful
to a regular person, not just data people.

### Design
- [ ] Warning taxonomy: fails EP (state), fails EP (national), fails D/E, insufficient
      data. Plain-language copy for each, reviewed against over-claiming risk (a warning
      describes the data, never "don't attend").
- [ ] Page design: search by school → program list with flags; program page with EP and
      D/E shown against benchmarks; caveats block on every page.
- [ ] Precompute strategy: static JSON shards per school (no backend).

### Code
- [ ] SQL: Value Check flag table from spine + FVT mirror (prefer ED official values;
      Scorecard fields as fallback, provenance column says which).
- [ ] Static site generator: school index + per-program pages from the flag table.
- [ ] Search (client-side index) + shareable URLs per program.

### Test
- [ ] Flag logic unit tests, including edge cases: suppressed earnings, missing debt,
      programs on ED site but not Scorecard and vice versa.
- [ ] Reconciliation: national failure counts on Truewise = counts from the raw FVT file.
- [ ] Copy review: every warning renders with its data provenance and cohort year.
- [ ] Accessibility pass (keyboard nav, contrast, screen-reader labels on flags).

### Implement / Deploy
- [ ] Deploy Value Check to truewise.us behind a clear nav entry.
- [ ] Methodology page v1: how flags are computed, data vintages, limitations.
- [ ] OG share-card image per program page (v2.2: moved up from Iteration 11; share cards
      are the reach unit during the news window).
- [ ] Publish the flag table as stable, versioned JSON endpoints (static files) for
      non-Python users.
- [ ] Spanish-language versions of the warning pages (templated; ship here or within one
      iteration after).

### ✅ Verify gate
- [ ] 20-program manual audit: flags match ED's published values exactly.
- [ ] A non-technical person can find a given program and correctly explain its warning
      (hallway usability test with 1–2 people).
- [ ] Lighthouse: performance + accessibility ≥ 90 on program pages.
- [ ] Share a program URL; it renders correctly with no local state.

---

## Iteration 4 — Public artifacts: package, write-up, press (~2–3 days)

**Goal:** convert the built spine into adoption engines: pip package, methodology
write-up, first press pitches, STATS what-if analysis.

**Use case, in plain terms:** a data analyst at a think tank wants to study college value.
Instead of rebuilding everything from scratch, they type `pip install truewise-data` and
have clean tables in Python within two minutes. A reporter on deadline reads your write-up
("these programs pass today's rules but would fail next year's") and quotes it with a link.
This iteration is when other people start building on your work, which is the entire
reputation engine.

### Design
- [ ] `truewise-data` API design: `load_institutions()`, `load_programs()`,
      `load_value_check()`, `load_fvt_snapshots()`; returns DataFrames or DuckDB relations.
- [ ] Write-up outline: reproducing the federal EP metric from public data + the STATS
      impact analysis (v2.2: rule is FINAL, effective 2027-07-01): programs that WILL lose
      Direct Loan eligibility, plus the grad-program exposure list (grads earning less than
      typical bachelor's holders) and the tipped-occupations carve-out.
- [ ] Press list: Higher Ed Dive, Inside Higher Ed, Hechinger, plus 2 local outlets for
      states with notable failure counts.
- [ ] 50 auto-generated state fact sheets ("X programs in [state] fail the earnings test")
      as the local-press hook (one template).

### Code
- [ ] Build the package (pyproject, typed, documented, versioned to data releases).
- [ ] STATS what-if notebook → reproducible script in `analysis/`.

### Test
- [ ] Package: `pip install truewise-data` in a fresh venv; quickstart from README runs
      top-to-bottom.
- [ ] What-if numbers reconcile against the Value Check flag table.
- [ ] A friend/colleague runs the quickstart cold and succeeds (external usability test).

### Implement / Deploy
- [ ] Publish to PyPI (v0.1.0); README badges (PyPI, DOI, CI).
- [ ] Submit the dataset to Data Is Plural at first release (highest-leverage channel for
      this artifact).
- [ ] Embeddable warning-card widget (one script tag) published with docs; offer it in
      every partner email.
- [ ] Publish write-up on the site blog + cross-post (dev.to / Medium); Zenodo DOI for the
      PDF version.
- [ ] Send press pitches with the what-if analysis as the hook; log every send.
- [ ] Submit a PyData / csv,conf talk proposal using this material.

### ✅ Verify gate
- [ ] PyPI page live; install works on a machine that never saw the repo.
- [ ] Write-up public, citable (DOI), linked from methodology page.
- [ ] At least 3 pitches sent and logged; talk proposal submitted.

---

## Iteration 5 — Design system & shared profile pages (~2–3 days)

**Goal:** one coherent product shell so every later module slots in.

**Use case, in plain terms:** before this, Truewise is a couple of useful but disconnected
pages. After this, a visitor can look up any US college and land on a proper profile page:
who the school is, its size and sector, and its Value Check results, all in one consistent
design. It starts feeling like one product instead of a stack of demos, and every future
feature will appear as a new section on this same page.

### Design
- [ ] Component inventory: nav, school header, metric card, chart, caveat block, footer
      with data vintage.
- [ ] School profile page layout that Value Check links into and future modules extend.

### Code
- [ ] Extract components from Value Check pages into the shared system.
- [ ] School profile page generator (identity, sector, size, links to modules).

### Test
- [ ] Visual regression snapshots for core components.
- [ ] All existing Value Check pages re-render identically through the new system.

### Implement / Deploy
- [ ] Deploy re-skinned site; profile pages live for all institutions.

### ✅ Verify gate
- [ ] Every Value Check program page reachable from its school profile and back.
- [ ] No broken links site-wide (crawler check in CI).

---

## Iteration 6 — Affordability matcher (~4–6 days)

**Goal:** net price by family income bracket on every school profile. Credits
TuitionTracker as prior art; differentiator is integration with warnings + open data.

**Use case, in plain terms:** a family earning $55,000 sees a college advertising $78,000
per year and crosses it off the list. On Truewise they pick their income range once and
every school page now shows what families LIKE THEM actually paid, often a fraction of the
sticker price. They can also rank schools by that real price. The product now answers the
two questions that matter most together: "can we afford it?" and "is it worth it?"

### Design
- [ ] Income-bracket UX: single selector, persisted across pages (URL param, no backend).
- [ ] Ranking view spec: "schools like X, cheaper for your bracket" with honest framing
      ("students like you paid roughly," cohort year labeled).

### Code
- [ ] SQL: net-price-by-bracket tables (Scorecard NPT4 fields) into the spine.
- [ ] Profile page section + ranking/filter page; static shards per state/sector.

### Test
- [ ] Spot-check 10 schools against ED published net price data.
- [ ] Bracket edge cases: missing brackets, private vs public program differences.
- [ ] Usability: bracket selection survives navigation.

### Implement / Deploy
- [ ] Deploy; dataset release bumped (new tables + changelog + DOI).

### ✅ Verify gate
- [ ] Manual audit of 10 school/bracket pairs matches source data.
- [ ] TuitionTracker credited on the methodology page.
- [ ] Organic search: affordability pages indexed (submit sitemap, verify in Search Console).

---

## Iteration 7 — ROI analyzer (~3–4 days)

**Goal:** field-of-study earnings vs debt, payback time, completion-weighted ROI.

**Use case, in plain terms:** a student torn between majoring in graphic design or nursing
at the same school can now compare them side by side: what graduates typically earn, what
they typically borrow, and roughly how many years it takes for the degree to pay for
itself. The numbers also account for the chance of actually finishing. It turns "follow
your passion vs be practical" from a shouting match into a look at the same screen.

### Design
- [ ] ROI formula spec (documented, comparable to CEW's approach, differences explained).
- [ ] Program-page section: earnings curve, debt, payback estimate with assumptions box.

### Code
- [ ] SQL: ROI metric tables; completion-weighting from graduation rates.
- [ ] Charts + assumptions UI on program pages.

### Test
- [ ] Unit tests on formula edge cases (zero debt, suppressed earnings, part-time heavy).
- [ ] Cross-check a sample against CEW's published rankings; explain divergences.

### Implement / Deploy
- [ ] Deploy; dataset + package release bump (`load_roi()`).

### ✅ Verify gate
- [ ] 10-program audit: ROI numbers reproducible by hand from published inputs.
- [ ] Methodology page updated; CEW comparison documented.

---

## Iteration 8 — Social mobility + repayment risk (~4–6 days)

**Goal:** Opportunity Insights mobility metrics + FSA repayment data; "hidden gems" view.

**Use case, in plain terms:** a first-generation student assumes only famous colleges
change lives. The hidden-gems page shows schools that quietly take in many low-income
students and launch them into the middle class, schools that rarely appear in rankings.
A counselor can pull up this list for a student and say "these schools have a track record
with students exactly like you," and back it with data on whether past students managed to
repay their loans.

### Design
- [ ] Mobility metric selection (access × success rate) and hidden-gems criteria.
- [ ] Repayment-risk framing that avoids stigmatizing schools serving low-income students
      (show context: Pell share, sector).

### Code
- [ ] Ingest Opportunity Insights tables + FSA repayment; join via crosswalk (OPEID).
- [ ] Profile sections + hidden-gems explorer page.

### Test
- [ ] Crosswalk coverage measured (OI uses grouped institutions; document match rate).
- [ ] Spot-checks against OI's published tables.

### Implement / Deploy
- [ ] Deploy; dataset/package bump; pitch a "hidden gems" story to one outlet.

### ✅ Verify gate
- [ ] Hidden-gems list manually reviewed for defensibility (no tiny-cohort artifacts).
- [ ] All new metrics carry provenance + cohort labels.

---

## Iteration 9 — Career section (~4–7 days)

**Goal:** major-to-career explorer (CIP→SOC) and grad-program ROI.

**Use case, in plain terms:** a student who likes biology can now see where that major
actually leads: the real jobs people end up in, what those jobs pay in their state, and
whether demand is growing or shrinking. From any career they can jump back to "which
programs near me feed into this job." Someone weighing an expensive master's degree gets
the same honest treatment: typical earnings versus typical debt for that exact program.

### Design
- [ ] CIP→SOC crosswalk handling for one-to-many mappings (design the aggregation rule).
- [ ] Career page: wage percentiles (BLS OEWS), outlook, linked programs.

### Code
- [ ] Ingest BLS OEWS + O*NET + CIP-SOC crosswalk; career page generator.
- [ ] Grad-program ROI tables (Scorecard grad fields).

### Test
- [ ] Crosswalk unit tests (known majors map to expected occupations).
- [ ] Wage figures spot-checked against BLS published tables.

### Implement / Deploy
- [ ] Deploy career section; dataset/package bump.

### ✅ Verify gate
- [ ] End-to-end: pick a major → see careers → see wages → jump back to programs offering it.
- [ ] 5 crosswalk audits pass.

---

## Iteration 10 — K-12 section (~7–10 days)

**Goal:** advanced-course access, beating-the-odds schools, dual enrollment, FAFSA gaps.
Second join key (NCES IDs) enters the spine.

**Use case, in plain terms:** Truewise now helps before college. A parent can look up
their child's school district and see: does the high school even offer calculus, AP
courses, or dual-enrollment college credit? Which local schools get unusually strong
results given the students they serve? A counselor or local reporter can see which high
schools have the biggest share of seniors leaving federal aid unclaimed because nobody
filed the FAFSA, and target help there.

### Design
- [ ] NCES/CRDC/SEDA ingestion plan (bigger files; decide precompute grain: district vs school).
- [ ] Beating-the-odds definition (SEDA growth vs demographics), reviewed for fairness.
- [ ] FAFSA-gap view spec (FSA completion by high school vs district size).

### Code
- [ ] Ingest CCD, CRDC, SEDA; NCES ID identity layer; validation tests.
- [ ] Four module views precomputed to static shards; district/school profile pages.

### Test
- [ ] Row counts vs published NCES totals; suppression handling on small schools.
- [ ] Spot-check CRDC course-access numbers for 5 districts.
- [ ] Performance: largest state page loads < 3s on throttled connection.

### Implement / Deploy
- [ ] Deploy K-12 section; dataset/package bump; pitch a local-angle story (state-level
      FAFSA gaps) to 2 regional outlets.

### ✅ Verify gate
- [ ] District → school → view navigation works end-to-end in 3 states.
- [ ] All four K-12 views carry caveats + vintages; no small-cohort leakage.

---

## Iteration 11 — Automation, polish, formal launch (~2–3 days)

**Goal:** the platform maintains itself; launch moment executed.

**Use case, in plain terms:** for visitors, nothing looks different, and that is the
point: the numbers quietly stay current every month without you touching anything, and
every page says how fresh its data is. For you, this is the iteration where Truewise stops
being a project you run and becomes a service that runs itself, freeing you to start
project #2 while Truewise keeps earning citations, users, and press mentions.

### Design
- [ ] Refresh calendar: annual full rebuild + monthly FVT snapshot + monthly link check.
- [ ] Launch checklist: announcement post, HN/Reddit (r/datasets, r/ApplyingToCollege
      where rules allow), newsletter pitches, partner emails.

### Code
- [ ] GitHub Actions: scheduled full refresh with schema-drift alerts to email/issue.
- [ ] 404/sitemap/OG images/SEO meta finalization.

### Test
- [ ] Dry-run the full annual refresh from scratch; time it; verify diffs are sane.
- [ ] Simulate a schema-drift failure; confirm the alert fires and deploy is blocked.

### Implement / Deploy
- [ ] Launch announcement published; JOSS submission prepared (repo will be 6 months
      public ~Jan 2027); partner outreach emails sent (NCAN, uAspire, ASCA lists).

### ✅ Verify gate
- [ ] One unattended scheduled refresh completes and deploys with zero manual steps.
- [ ] Impact log reviewed: every artifact (site, dataset DOIs, PyPI, write-ups, pitches,
      talks, partners) has dated evidence collected to date.

---

## Milestone map

| Milestone | Iterations | Target |
|---|---|---|
| M1 news-window MVP (spine + monitor + Value Check + artifacts) | 0–4 | ~3–4 weeks from start; well before 2026-10-01 |
| M2 college suite | 5–8 | ~8–10 weeks |
| M3 careers | 9 | ~11–12 weeks |
| M4 K-12 + launch | 10–11 | ~14 weeks |

_Effort assumes focused part-time days per plan v2.1. If time pressure hits, cut from the
bottom (K-12 → careers), never from iterations 0–4._
