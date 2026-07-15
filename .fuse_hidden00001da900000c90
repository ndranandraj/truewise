# Truewise — Project Plan v2 (Reputation-First)

_Written 2026-07-06, revised same day to v2.1 after review. Revised to v2.2 on 2026-07-13:
the STATS rule was FINALIZED 2026-07-01 (section 2 updated, "what-if" upgraded to "what-will"),
plus accessibility and reach upgrades (new section 7b). Supersedes the build ordering in
PLAN.md; all architecture, data-source, and scope decisions there still stand. This version
reorders the roadmap around the July 2026 FVT/GE news window and bakes in reputation
instrumentation (job market, EB-1A/NIW evidence, public visibility)._

## 1. Mission (unchanged)
Replace the scary or hidden number with the real one, from public federal education data.
Positive, opportunity-opening framing.

## 2. What changed and why

The federal Financial Value Transparency / Gainful Employment framework took effect
July 1, 2026, and **ED's program-level transparency website launched July 1, 2026 and is
live now** (verified 2026-07-06), publishing debt-to-earnings rates and earnings-premium
figures per program. The final FVT/GE reporting cycle runs July 1 to October 1, 2026, and
low-earning programs must give prospective students warnings. Education press will cover this
all year. Truewise's Value Check module mirrors this framework exactly, so it moves from
"build early" to "build first after the spine." The Affordability matcher is evergreen and
moves to second.

**Regulatory update (v2.2, verified 2026-07-13): STATS is FINAL, not proposed.** ED published
the final STATS / Earnings Accountability rule in the Federal Register on 2026-07-01 (nearly
10,000 comments on the April NPRM). It drops D/E and relies on the earnings-premium metric
alone: undergraduate programs must show grads out-earn a typical high-school grad; graduate
programs must show grads out-earn a typical bachelor's holder. A program failing 2 of 3
consecutive award years loses Direct Loan eligibility. Most provisions effective 2027-07-01;
some technical/administrative provisions 2026-08-31. Consequences for Truewise:
(a) 2026 is confirmed as the FINAL FVT/GE reporting cycle and D/E will be retired, so the
independent archive is certain (not speculative) historical value — snapshot ED's site NOW;
(b) the planned "what-if" upgrades to a **"what-will" analysis**: which programs will lose
loan eligibility under the final rule — concrete, dated, more quotable;
(c) new original angle nobody has published: **grad-program exposure** (master's/doctoral
programs whose grads earn less than typical bachelor's holders);
(d) quirky quotable finding: programs feeding tipped occupations (e.g., cosmetology) get
delayed consequences because of the No Tax on Tips earnings-data lag.

Second change: every milestone now ships a public, adoptable artifact (dataset, package,
write-up), because measurable adoption is what converts a portfolio project into hiring
evidence and EB-1A/NIW evidence.

## 3. Reputation goals and how the plan serves them

- **Job market:** end-to-end pipeline (DuckDB, Parquet, CI, tests, static frontend) plus a
  shipped public product. Each phase produces something demoable in an interview.
- **EB-1A/NIW:** USCIS accepts widely adopted open-source tools, published datasets,
  adoption metrics, press coverage, and letters from independent users. The plan therefore
  publishes a pip package and dataset (countable downloads), a methodology write-up
  (authorship), and pitches press (published material about the work). National importance
  is straightforward: college affordability and student debt.
- **Visibility:** ride the FVT/GE news cycle in 2026; talks at PyData / csv,conf / civic
  tech meetups; methodology post that journalists and researchers can cite.

## 4. Public artifacts (new, first-class deliverables)

1. **`truewise-data` pip package** — loads cleaned Scorecard + FVT/GE tables as DataFrames
   or DuckDB relations. Small, documented, versioned with the annual refresh.
2. **Published dataset** — the cleaned, joined Parquet spine on GitHub Releases and
   Hugging Face Datasets, with a data dictionary and license (CC-BY).
3. **Methodology write-up** — "Reproducing the federal earnings-premium metric from College
   Scorecard data": blog post plus a citable PDF. Doubles as the site's methodology page.
4. **Impact log** — a private running file of every mention, user email, nonprofit or
   counselor use, star, download stat, and traffic report. Screenshot everything with dates.
   This is the hardest evidence to reconstruct later; start it at repo creation.

## 5. Revised build order

| Phase | What | Effort | Reputation artifact |
|---|---|---|---|
| 0 | Repo (make PUBLIC immediately: starts the 6-month JOSS clock), CI skeleton, branding, register truewise.us, start impact log | ~1 day | Public repo |
| 0b | FVT/GE monitor: first snapshot of ED's live transparency site (archive before anything changes) | ~0.5 day | Dated raw archive |
| 1 | Data spine v1: Scorecard ingest, UnitID/OPEID identity layer, DuckDB/Parquet, validation tests | ~3–4 days | Dataset v0 published |
| 2 | **Value Check module** (was phase 4): earnings-premium flags (state + national), debt-to-earnings, plain-language warnings, shared school/program profile page | ~4–5 days | The news-cycle feature |
| 3 | Methodology write-up + press outreach (Higher Ed Dive, Inside Higher Ed, Hechinger Report); publish `truewise-data` v0.1 | ~2 days | Write-up, package, pitches |
| 4 | Design system, nav shell, caveats page | ~2–3 days | Polished demo |
| 5 | Affordability matcher (was phase 2): net price by income bracket | ~4–6 days | Second module |
| 6 | ROI analyzer (field-of-study earnings/debt, payback, completion-weighted) | ~3–4 days | College suite complete |
| 7 | Social mobility (Opportunity Insights), loan-repayment risk (FSA) | ~4–6 days | |
| 8 | Career section: CIP→SOC major-to-career, grad ROI | ~4–7 days | |
| 9 | K-12 section: course access, beating-the-odds, dual enrollment, FAFSA gaps | ~7–10 days | |
| 10 | Refresh automation (GitHub Actions), monitoring, launch polish | ~2–3 days | |

**MVP for the news window = phases 0–3, roughly 2 weeks part-time.** Target: Value Check
live and pitched before the October 1, 2026 FVT/GE reporting deadline generates the next
wave of coverage.

## 6. FVT/GE monitor (new sub-module, upgraded in review)

ED's transparency site is live as of July 1, 2026, so this starts immediately rather than
"when published":

- **Mirror + archive from day one** (raw snapshots, dated, committed to the repo or
  releases). With the STATS proposal potentially retiring D/E in 2027, today's snapshots
  become the only independent historical record. Archiving government data before it
  changes is a recognized civic-tech contribution.
- **Diff on every refresh:** programs newly failing, revised figures, removed rows.
  Each interesting diff is a content/press opportunity.
- **Cross-validation:** check Scorecard earnings-premium fields against ED's official
  site values; discrepancies are themselves findings.
- **STATS impact analysis (upgraded in v2.2; rule now final):** publish "programs that will
  lose Direct Loan eligibility under the final STATS rule (effective 2027-07-01)." Add two
  companion pieces: the grad-program exposure list (master's programs whose grads earn less
  than typical bachelor's holders) and the tipped-occupations carve-out finding. Original,
  quotable, and cheap once the mirror exists.

Est. ~2–3 days on top of the spine.

## 7. Publication, judging, awards, and partnership track (added in v2.1 review)

The v2 plan covered adoption and press; these four channels were missing. Each maps to a
distinct EB-1A criterion and none costs more than a few days across the year.

- **Citable peer-reviewed paper (JOSS).** The Journal of Open Source Software is free,
  peer-reviewed, and mints a CrossRef DOI. Requirement that drives scheduling: **the repo
  must be public with 6+ months of active development before submission.** Make the repo
  public at phase 0 (July 2026) → eligible to submit `truewise-data` around January 2027.
  Also mint a Zenodo DOI for each dataset release immediately (no waiting period), so
  researchers can cite the data from day one.
- **Judging others' work.** After the JOSS paper, volunteer as a JOSS reviewer; also offer
  to review PyData / csv,conf talk proposals. "Judging the work of others" is its own
  EB-1A criterion and currently has no coverage in the plan.
- **Awards calendar.** Sigma Awards (data journalism, entries each winter for work
  published that year): a collaboration with a reporter using Truewise data can be entered.
  Watch for civic-tech and open-data award calls; log every submission in the impact log.
- **Partnerships → independent-user letters.** Offer Value Check warnings as free embeds
  or data feeds to college-access nonprofits (NCAN members, uAspire), school counselor
  networks (ASCA), and state higher-ed agencies. Each adopting organization is measurable
  adoption now and a recommendation-letter source later. Target: first partner org by
  October 2026.
- **SEO as an adoption metric.** Generate a static page per program/school (thousands of
  long-tail pages). Organic search traffic is quantifiable reach evidence; publish the
  dataset on Hugging Face AND Kaggle, both of which display download counts publicly.

## 7b. Accessibility & reach upgrades (added v2.2, 2026-07-13)

The plan served data people well but under-served regular families and distribution. Seven
additions, all cheap on a static templated site:

1. **Spanish-language Value Check pages.** Warnings are templated; translation is nearly
   free and first-gen/immigrant families are exactly the audience for plain-language
   warnings. No competitor does this. Ship with or shortly after Iteration 3.
2. **Embeddable widget as a first-class M1 artifact** (not an afterthought of the
   partnership track): one script tag renders a program's warning card on any counselor or
   nonprofit site. Every embed = adoption evidence + backlink.
3. **Stable JSON endpoints** for the flag table (static files, versioned URLs), so
   journalists and web developers who will never `pip install` can still build on Truewise.
4. **OG/social share-card images per program page moved from Iteration 11 to Iteration 3.**
   Program pages with warning cards are the shareable unit; launching without share cards
   wastes the news window.
5. **50 auto-generated state fact sheets** ("X programs in Texas fail the earnings test").
   One template, 50 local press angles; local outlets are far easier to land than national.
   Attach to Iteration 4 press outreach.
6. **Submit the dataset to Data Is Plural** (Jeremy Singer-Vine's newsletter) at first
   release. Single highest-leverage channel for exactly this artifact.
7. **AI-citability:** clean structured data (schema.org), llms.txt, per-page provenance and
   data vintage. Families increasingly ask chatbots "is this program worth it"; be the
   source that gets cited. Near-zero cost on a static site.

## 8. Everything unchanged from PLAN.md

Architecture (shared spine + modules, static-first hosting, DuckDB + Parquet), data sources
(DATA_SOURCES.md), hardware verdict (MacBook Air fine), cost (~$0 plus ~$5–10/yr domain),
cut scope (transfer-credit planner cut; apprenticeships optional; Pell folded in), and the
risks/mitigations table all stand. Open items from HANDOFF.md also stand, especially:
verify current Scorecard earnings-premium field names before building Value Check.
(The STATS question is answered: final rule published 2026-07-01; see section 2.)

## 9. Prior art / competitive landscape (verified 2026-07-06)

Prior-art check result: no single component is unprecedented, but the open-infrastructure
combination is unclaimed. Who does what today:

- **ED itself** (College Scorecard + the live FVT site): publishes the raw metrics but with
  limited UX, no plain-language warnings, no history, and data that gets revised.
- **HEA Group** (Michael Itzkowitz): publishes the "1 in 4 programs earn less than a high
  school grad" analyses that get national press (CBS etc.). One-off reports, closed
  methodology, no maintained lookup tool, not open source. Validates that press demand
  exists for exactly Value Check's finding.
- **Georgetown CEW ROI rankings**: polished interactive tool, 4,600 institutions, ROI over
  10/20/30/40-year horizons. Heavy overlap with the ROI module at institution level;
  weaker at program level and not reproducible/open.
- **TuitionTracker** (Hechinger, updated April 2026): net price by income bracket. Directly
  overlaps the Affordability matcher.
- **PyScorecard / pypeds**: thin API wrappers. No cleaned joined dataset package, no
  FVT/GE data included.
- **Nobody found doing:** an FVT/GE site mirror with dated archive + diffs, an open CC-BY
  joined Parquet dataset, a reproducible open pipeline, the STATS what-if analysis, or a
  maintained program-level plain-language warning lookup.

**Positioning consequence:** compete as open data infrastructure, not as another college
comparison site. The consumer-site framing puts Truewise against ED, CEW, and Hechinger,
who are better funded and already ranked in search. The infrastructure framing (dataset +
package + archive + methodology that researchers, journalists, and counselors build on) has
no incumbent, produces better adoption evidence, and makes HEA Group and CEW validation
rather than competition. The site remains the demo layer on top. Affordability matcher
stays second but should link to and credit TuitionTracker rather than claim novelty.

## 10. Definition of success (12 months)

- Value Check cited or linked by at least one national or trade outlet.
- 500+ downloads/month on `truewise-data`; measurable dataset downloads (HF + Kaggle).
- One conference or meetup talk delivered.
- Three or more independent users (counselors, researchers, nonprofits) documented in the
  impact log, candidates for future recommendation letters; first partner org by Oct 2026.
- JOSS paper submitted (~Jan 2027, after the 6-month public-repo window) and Zenodo DOIs
  on all dataset releases from the first release.
- STATS impact analysis (undergrad "what-will" list + grad-program exposure) published and
  pitched well before the rule's 2027-07-01 effective date makes it old news.
- Spanish Value Check pages live; at least 3 organizations using the embed widget.
- Full college suite (M2) live on truewise.us.
