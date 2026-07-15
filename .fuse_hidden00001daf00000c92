# Truewise — Education Data Platform

## What this is
A public-data platform that turns scattered US federal education data into clear, honest
guidance for students and families. Mission: replace the scary or hidden number (sticker
price, anecdote, unclaimed aid) with the real one, drawn from public data. Framing is
positive and opportunity-opening, not problem-cataloguing.

- **Name:** Truewise
- **Domain:** truewise.us (confirmed available June 2026; not yet registered — register at
  Cloudflare Registrar or Namecheap; .us requires a US nexus attestation at checkout)
- **Stage:** Planning complete, plan revised to v2.2 on 2026-07-13. Repo scaffold started
  (pipeline/, requirements.txt). Next steps: register domain + public repo + FIRST SNAPSHOT
  of ED's FVT site (time-critical), finish the Scorecard loader, build Value Check FIRST.

## Reputation strategy (drives all prioritization, added 2026-07-06)
Anand's goals for this work, in priority order: (1) US data science job market portfolio,
(2) EB-1A / EB-2 NIW immigration evidence (adoption metrics, press, independent-user
letters, authorship), (3) public/civic-tech visibility. Consequences:
- **Value Check moves to first module.** The federal FVT/GE framework took effect
  2026-07-01; final reporting cycle runs to 2026-10-01; press window is NOW.
- **STATS rule is FINAL (published 2026-07-01, verified 2026-07-13):** EP-only metric, D/E
  retired, grad programs measured vs bachelor's holders, fail 2 of 3 years → lose Direct
  Loan eligibility, mostly effective 2027-07-01. The "what-if" is now a "what-will"
  analysis; grad-program exposure list is an unclaimed press angle. See plan v2.2 §2, §7b.
- **Every milestone ships a public artifact:** `truewise-data` pip package, published
  Parquet dataset (GitHub/Hugging Face, CC-BY), methodology write-up, press pitches
  (Higher Ed Dive, Inside Higher Ed, Hechinger Report), talks (PyData, csv,conf).
- **Impact log from day one:** record every mention, user, download stat, with dates.
  Hardest evidence to reconstruct later.
See `Truewise - Project Plan v2 (Reputation-First).md` for the full revised plan and
`Reputation Strategy - Project Ideas Review.md` for the reasoning.

## Project #2 (queued, do NOT start until Truewise M1/M2 ships)
**Hospital Price Transparency Cleaning Toolkit** (working name MRF Clean): open validator +
normalizer for hospital machine-readable files against the CMS v3.0 schema (effective
2026-01-01, enforcement 2026-04-01), plus a quarterly "Hospital MRF Quality Index" as the
press artifact. Hospital files only; payer TiC files out of scope. Full plan:
`Hospital Price Transparency Toolkit - Project Plan.md`.

## Core architecture
One shared data warehouse over the major federal education datasets, joined on common
school identifiers, with interchangeable "modules" (each project idea) built on top. Build
the spine once, reuse it for every module.

- **Join keys:** colleges = IPEDS UnitID / OPEID; K-12 = NCES IDs; geography = FIPS.
- **Hybrid, static-first:** precompute every module's outputs in CI and serve a static
  site (no backend hosting, $0, no cold starts). Add a single FastAPI endpoint later only
  if one module needs heavy live cross-filtering.

## Tech stack
- Data: bulk CSV downloads → DuckDB + Parquet (SQL transforms, optional dbt)
- Analysis/modeling: pandas, scikit-learn; GeoPandas for maps
- Optional backend: FastAPI
- Frontend: React or lightweight vanilla JS + Recharts/Chart.js, MapLibre for maps
- Automation: GitHub Actions (annual full refresh + monthly update checks)
- Hosting: Cloudflare Pages / Netlify / GitHub Pages (static). Backend if needed: Render
  free tier (cold starts) or ~$5/mo.

## Data sources (all public, free)
College Scorecard (net price by income, ROI, completion, field-of-study earnings),
IPEDS, Federal Student Aid (FAFSA completion, repayment), Opportunity Insights (mobility),
NCES Common Core of Data, Civil Rights Data Collection, SEDA, BLS/O*NET, Census ACS.

## Data footprint / hardware
"Medium data," not big data. Raw downloads ~3–8 GB; Parquet working set ~1–3 GB. Largest
tables are a few million rows. A MacBook Air (even 8 GB) handles this comfortably via
DuckDB (streams/spills to disk). No GPU needed. Keep ~30–40 GB free during the build.

## Module roadmap (v2 ordering, 2026-07-06; supersedes v1 which had affordability first)
1. **Value Check** (FLAGSHIP, BUILD FIRST after the spine): flags programs whose grads earn
   below a typical high-school grad (state + national) and surfaces debt-to-earnings.
   Mirrors the federal Financial Value Transparency & Gainful Employment framework
   (effective July 1, 2026). Uses Scorecard's EXISTING earnings-premium fields, no new
   dataset. The sharpest "honest number" feature and the 2026 news hook. Includes the
   FVT/GE monitor sub-module (mirror + diff ED's transparency site data each refresh).
2. **Affordability matcher** (was first; now second, evergreen). Net price by family
   income bracket; forces the shared school profile page.
3. **ROI analyzer** (field-of-study earnings/debt, payback, completion-weighted)
4. Social mobility index (Opportunity Insights)
5. More college modules: loan-repayment-risk (Pell-success folded into affordability +
   mobility rather than a separate module)
6. Career section: major-to-career (CIP→SOC crosswalk), grad ROI; apprenticeships optional
   (separate DOL data, not the shared spine)
7. K-12 section: advanced-course access, beating-the-odds, dual enrollment, FAFSA gaps

### Cut / rescoped for accuracy
- **Transfer-credit planner — CUT.** "Which credits transfer where" lives in state
  articulation agreements, not in federal data; IPEDS only has transfer-out counts. Not
  buildable from these sources; cut to avoid overpromising.
- **Apprenticeship finder — optional bolt-on.** Uses a separate DOL system
  (Apprenticeship.gov / RAPIDS), so it doesn't join the shared spine.
- **Pell-success view — merged** into the affordability + mobility modules (was redundant).

## Effort & cost
MVP (spine + affordability + design system): ~2–3 weeks part-time. Strong college product:
~5–7 weeks. Full platform: ~10–14 weeks. Cost ~$0 (static); ~$5–10/yr for the domain.

## Key decisions & context
- **Revenue expectation: ~$0 direct.** Treated as a portfolio/skills/social-impact piece,
  not a business. Hence the deliberate low domain spend (cap ~$50/yr). Affiliate/lead-gen
  is the only real money path but needs heavy traffic; not the goal.
- **Name history:** rejected EdCompass, Pellwise, Costlas (taken or cost-scoped/narrow).
  EdScout and EduSearch domains were available but collide with existing same-space
  companies. Truewise chosen: distinctive, "-wise" is friendly, "true" fits the mission,
  no same-space conflict, and truewise.us is cheap + available.
- **Hosting reality (2026):** backend free tiers tightened — Fly.io dropped free tier for
  new accounts, Railway is ~$5/mo for anything real, Render free service cold-starts. This
  is why the architecture leans static.

## Deliverables in this folder
- `Truewise - Project Plan v2 (Reputation-First).md` — CURRENT plan (build order + artifacts)
- `Truewise - Iteration Plan & Checklist.md` — execution checklist (12 iterations, each
  design→code→test→implement + deploy/verify gate)
- `PLAN.md` — v1 full plan (architecture/data/risks still valid; ordering superseded by v2)
- `HANDOFF.md` — decisions log and open questions
- `DATA_SOURCES.md` — dataset URLs, grain, key fields, join keys
- `Reputation Strategy - Project Ideas Review.md` — goals analysis + ranked project ideas
- `Hospital Price Transparency Toolkit - Project Plan.md` — full plan for queued project #2
- `Truewise - Education Data Platform Plan.pdf` — original formatted platform plan
- `College ROI Analyzer - Project Plan.pdf` — earlier standalone ROI plan (now the ROI module)
- `pipeline/`, `requirements.txt`, `.gitignore` — repo scaffold
