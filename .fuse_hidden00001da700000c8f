# Truewise — Education Data Platform (Full Plan)

_Last updated: 2026-07-06. This is the model-readable version of
`Truewise - Education Data Platform Plan.pdf`._

## 1. Vision and mission
Every module shares one mission: replace the scary or hidden number with the real one.
Students rule out affordable colleges because they only see sticker price, miss aid they
qualify for, pick majors on anecdote, and overlook schools that quietly change lives.
Truewise gives them honest numbers from public data, presented simply. The framing is
positive and opportunity-opening, not problem-cataloguing.

## 2. Unifying architecture
Build one shared data warehouse over the major federal education datasets, joined on common
school identifiers, with interchangeable "modules" on top. Build the spine once, reuse it.

Join keys:
- Colleges = IPEDS **UnitID** (and OPEID)
- K-12 schools/districts = **NCES IDs**
- Geography = **FIPS** / ZIP / state

Shape: a shared data spine plus interchangeable modules. One ingestion-and-refresh pipeline
pulls bulk files, cleans them, and lands them in DuckDB / Parquet. Every module reads from
that one source. Add a dataset once and any number of modules can use it.

## 3. Data sources
See DATA_SOURCES.md for URLs and fields. Summary: College Scorecard, IPEDS, Federal Student
Aid, Opportunity Insights, NCES Common Core of Data, Civil Rights Data Collection, SEDA,
BLS/O*NET, Census ACS. All free and public. College Scorecard last refreshed 2026-06-10.

## 4. Data footprint, storage, and compute
"Medium data," not big data. Mostly plain tabular CSV: one row per school, or per
school-and-program, or per school-and-year. Widest file (Scorecard institutions) is ~6,500
rows x ~3,000 cols; largest by row count are K-12 files at ~100,000 schools. Biggest single
table is a few million rows.

- Raw downloads: ~3–8 GB if grabbing everything. Parquet working set: ~1–3 GB.
- Keep ~30–40 GB free during the build (scratch for downloads/unzips); steady-state a few GB.
- DuckDB runs locally, no server, streams/spills to disk, so it handles tens of GB on 8 GB RAM.
- Optional scikit-learn model trains in seconds to minutes on CPU. No GPU needed.
- **Hardware verdict:** a MacBook Air (even 8 GB) handles this comfortably. Bottleneck is
  design time, not hardware. Only real constraints: disk during download; pull Census ACS
  selectively (it can balloon).

## 5. Module catalog
Grouped by audience so the site reads as coherent navigation.

**Choosing & paying for college** (College Scorecard, IPEDS, FSA, Opportunity Insights)
- Affordability matcher (net price by income) — BUILD FIRST
- ROI analyzer (field-of-study earnings/debt, payback, completion-weighted)
- **Value Check** (earnings-premium & debt-to-earnings warning) — FLAGSHIP, build early
- Social-mobility index (Opportunity Insights)
- Loan-repayment-risk view

**Career & pathways** (College Scorecard field-of-study, BLS, O*NET, DOL)
- Major-to-career outcomes explorer (CIP→SOC crosswalk)
- Graduate-program ROI
- Apprenticeship finder — OPTIONAL bolt-on (separate DOL data, not the shared spine)

**K-12 opportunity** (CRDC, NCES CCD, SEDA, FSA)
- Advanced-course access
- "Beating the odds" schools
- Dual enrollment access
- FAFSA completion gaps

**Connective tissue:** a shared school/program profile page any module can deep-link into.
This makes Truewise one product, not a dashboard junk drawer.

### Value Check (why it's the flagship)
The federal Financial Value Transparency & Gainful Employment framework takes effect
2026-07-01, judging every program on two tests: debt-to-earnings ratio and an earnings
premium (do graduates out-earn a typical high-school grad in their state). College Scorecard
ALREADY publishes the earnings-premium comparison (state + national), and the 2026–27 FAFSA
will flag schools whose graduates earn less than a typical high-school grad. Value Check
turns this into a plain-language warning, mirrors the government's own accountability
metrics, and needs no new dataset. Sharpest "honest number" feature on the platform.

### Deliberately cut / rescoped (for accuracy)
- **Transfer-credit planner — CUT.** "Which credits transfer where" lives in state
  articulation agreements, not federal data; IPEDS only has transfer-out counts. Not
  buildable from these sources. Cut to avoid overpromising.
- **Apprenticeship finder — optional bolt-on.** Separate DOL system (Apprenticeship.gov /
  RAPIDS); doesn't join the shared spine.
- **Pell-success view — merged** into affordability + mobility modules (was redundant).

## 6. Tech stack
- Ingestion: Python (requests, pandas)
- Storage/query: DuckDB + Parquet (DuckDB-WASM can run in-browser for the static path)
- Transform: SQL in DuckDB (optional dbt)
- Analysis/modeling: pandas, scikit-learn
- Geospatial: GeoPandas; maps via MapLibre
- Backend (optional): FastAPI
- Frontend: React or lightweight vanilla JS + Recharts/Chart.js
- Automation: GitHub Actions (annual full refresh + monthly update checks)
- Testing: pytest + data-validation checks (catch schema drift / broken joins on refresh)

## 7. Architecture: two paths (recommended = hybrid, static-first)
- **Path A — Static precompute:** CI computes all module outputs, writes Parquet/JSON (or
  ships DuckDB-WASM); browser queries static files. No backend, $0, no cold starts.
  Excellent fit because the data is static between annual refreshes.
- **Path B — FastAPI backend:** serves live queries from DuckDB; React calls the API.
  Adds full-stack experience; costs $0–$5/mo; free tiers cold-start.
- **Recommended:** start static (Path A). If one module later needs heavy live
  cross-filtering, add a single FastAPI endpoint just for that. Clean upgrade path.

## 8. Hosting and cost
- Code + pipeline: GitHub + GitHub Actions — $0
- Static site: Cloudflare Pages / Netlify / GitHub Pages — $0
- Optional backend: Render free tier (cold starts) or ~$5/mo always-on
- Domain: truewise.us ~$5–10/yr (.us requires US nexus attestation at checkout)
- **Effective total:** $0 (≈$5–10/yr with the domain).

2026 hosting reality: backend free tiers tightened. Fly.io dropped its free tier for new
accounts; Railway is effectively a one-time $5 trial then $1/mo for a tiny service; Render's
free web service spins down after 15 min idle and cut bandwidth to 5 GB/mo. Static hosting
sidesteps all of it.

## 9. Build phases and effort (focused part-time days)
0. Foundation — repo, structure, env, CI skeleton, branding. ~1 day
1. Data spine v1 — ingest College Scorecard; build college identity layer (UnitID/OPEID);
   land in DuckDB/Parquet; schema + validation tests; document suppressed-value handling. ~3–4 days
2. Affordability matcher — net-price-by-income queries; ranking; shared profile page;
   income/filter UI; charts. ~4–6 days
3. Design system — shared UI components, nav shell, methodology/caveats page. ~2–3 days
4. ROI + Value Check module — field-of-study earnings/debt; payback + completion-weighted
   ROI; Value Check flags below-HS-grad earnings + debt-to-earnings (Scorecard fields). ~4–5 days
5. Social mobility module — add Opportunity Insights; mobility index; "hidden gems." ~2–3 days
6. More college modules — loan-repayment-risk (adds FSA); fold Pell-success in. ~3–5 days
7. Career section — add BLS + O*NET; major-to-career (CIP→SOC); grad ROI; apprenticeship
   optional. ~4–7 days
8. K-12 section — add NCES CCD + CRDC + SEDA (second join key); course access,
   beating-the-odds, dual enrollment, FAFSA gaps. ~7–10 days
9. Refresh automation — GitHub Actions annual + monthly; alert on schema drift. ~1–2 days
10. Polish + launch — accessibility, performance, About/methodology, SEO, launch. ~2–3 days

**Totals:** MVP (0–3) ~2–3 weeks part-time. Strong college product ~5–7 weeks. Full
platform ~10–14 weeks.

## 10. Risks and mitigations
- Suppressed/missing data (small cohorts) → show "insufficient data"; never silently impute.
- Data lags 1–2 years → label cohort years; frame as "students like you paid/earned roughly."
- Join-key mismatches → documented crosswalk in phase 1; validation tests every refresh.
- Scope creep across modules → ship MVP first; each module is an optional increment.
- Over-claiming (tool as verdict) → consistent caveats; point to official Net Price
  Calculators / advisors for personal numbers.
- Large K-12 files → DuckDB columnar queries; precompute so the browser never loads raw files.

## 11. Roadmap milestones
- M1 — MVP: data spine + affordability matcher + shared profile page
- M2 — College suite: ROI, Value Check, social mobility, repayment risk
- M3 — Careers: major-to-career, grad ROI, apprenticeships (optional)
- M4 — K-12 + launch: course access, beating-the-odds, dual enrollment, FAFSA gaps
