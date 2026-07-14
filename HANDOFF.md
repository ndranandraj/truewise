# Handoff & Decisions Log

_Written 2026-07-06 to hand this project to a fresh session (possibly a different model)._
_This captures the "why" behind the plan so you don't re-litigate settled decisions._

## Current status
(Updated 2026-07-13.) Planning complete; plan revised to v2.2 (see `Truewise - Project Plan
v2 (Reputation-First).md`, which supersedes the ordering below). No code beyond the
pipeline scaffold. Domain not yet registered. Immediate next steps: register truewise.us,
make the repo public (starts the JOSS clock), take the FIRST SNAPSHOT of ED's live FVT
transparency site (time-critical: 2026 is the final FVT/GE reporting cycle), then build the
spine and **Value Check first** (not the Affordability matcher — that ordering was v1).

## What was decided, and why

### Project identity
- **Name: Truewise.** Chosen after checking many alternatives. "-wise" is friendly, "true"
  fits the honest-numbers mission, and it's broad enough to cover the whole platform (not
  cost-scoped). No same-space company conflict found in searches.
- **Domain: truewise.us** — verified available 2026-07 (NXDOMAIN on SOA + NS). ~$5–10/yr.
  `.us` requires a US nexus attestation at checkout (must be US citizen/resident/org).
  Register at Cloudflare Registrar (at-cost) or Namecheap. NOT yet registered — user's
  next manual step.
- Rejected names and why:
  - **EdCompass, Pellwise, Costlas** — taken, or scope-limited to cost/aid (won't scale to
    K-12/career modules).
  - **EdScout, EduSearch** — domains were available (.us/.org) BUT collide with existing
    same-space education companies (EdScout AU school-finder; EduSearch Network US lead-gen).
    Weak/generic and confusing; rejected despite cheap domains.
  - Truewise.com/.org were taken (parked); truewise.io available (~$50) as a fallback.

### Business framing
- **~$0 direct revenue expected.** Treated as a portfolio / skills / social-impact piece,
  not a business. Audience is price-sensitive; data is public/copyable; incumbents are free.
- Only real money path is affiliate/lead-gen (student loans, refi, scholarships, 529s),
  which needs heavy traffic — not the goal. B2B licensing to counselors/nonprofits and
  small foundation grants are possible but effortful.
- Because revenue ≈ $0, **domain spend capped ~$50/yr**; hence .us at ~$5–10.

### Architecture
- **Shared data spine + modules**, joined on school IDs (UnitID for college, NCES for K-12).
- **Hybrid, static-first hosting.** Precompute module outputs in CI, serve a static site
  ($0, no cold starts) — the data is static between annual refreshes so this fits perfectly.
  Add one FastAPI endpoint later only if a module needs heavy live cross-filtering.
- Driven partly by 2026 hosting reality: backend free tiers tightened (Fly.io dropped free
  tier, Railway ~$5/mo, Render cold-starts). Static avoids all of it.
- **DuckDB + Parquet** is the core; runs fine on a MacBook Air (even 8 GB). Confirmed the
  data is "medium data" (~3–8 GB raw, ~1–3 GB parquet, few-million-row max tables).

### Scope changes made during planning (important — don't revert)
- **Added Value Check module (flagship).** Flags programs whose grads earn below a typical
  HS grad (state+national) + debt-to-earnings. Mirrors the federal Financial Value
  Transparency & Gainful Employment framework (effective 2026-07-01). Uses Scorecard's
  EXISTING earnings-premium fields — no new dataset. Build it early (folded with ROI).
- **Cut the transfer-credit planner.** Not buildable from federal data (credit transfer
  lives in state articulation agreements; IPEDS only has transfer-out counts). Cut to avoid
  overpromising.
- **Demoted apprenticeship finder to optional bolt-on** (separate DOL data, off-spine).
- **Merged Pell-success view** into affordability + mobility (was redundant).

## Open questions / decisions for the next session
1. Register truewise.us (manual, user action).
2. Confirm the exact Scorecard earnings-premium field names in the current data dictionary
   before building Value Check (they were added/expanded in 2025–2026 updates).
3. Decide frontend: React (more growth) vs vanilla JS (faster). Plan leans lightweight.
4. Decide whether to keep a module name for the affordability tool (e.g., an internal
   codename) — not required.
5. Whether to run as a nonprofit/civic project (affects grant eligibility) — deferred.

## Next actions (concrete, in order)
1. `pip install -r requirements.txt`; get a free Scorecard API key (api.data.gov/signup).
2. Finish `pipeline/load_scorecard.py`: download the Scorecard bulk "Most Recent" files,
   load institution + field-of-study tables into DuckDB, verify a UnitID join works.
3. Add validation tests (row counts, null rates, suppressed-value handling).
4. Build Module 1 (Affordability matcher): net-price-by-income ranking for a chosen bracket,
   plus the shared school profile page. Ship it end-to-end for a few schools before scaling.
5. Stand up the design system / nav shell so later modules slot in consistently.

## Reference files in this folder
- `CLAUDE.md` — condensed context (auto-loaded by AI).
- `PLAN.md` — full plan (modules, tech, cost, effort, phases, risks).
- `DATA_SOURCES.md` — dataset URLs, grain, key fields, join keys.
- `Truewise - Education Data Platform Plan.pdf` — formatted plan.
- `College ROI Analyzer - Project Plan.pdf` — earlier standalone ROI plan (now the ROI module).
- `requirements.txt`, `.gitignore`, `pipeline/load_scorecard.py` — repo scaffold.

## Facts worth re-verifying (they change)
- Hosting free-tier terms (Render/Railway/Fly.io) — checked 2026-07; re-check before deploy.
- Scorecard field names + latest refresh date.
- Financial Value Transparency / Gainful Employment status: effective 2026-07-01; ED's
  program-level transparency site live since 2026-07-01; final FVT/GE reporting cycle runs
  2026-07-01 → 2026-10-01.
- STATS / Earnings Accountability: FINAL rule published in the Federal Register 2026-07-01
  (verified 2026-07-13). EP-only metric (D/E retired); grad programs measured against
  bachelor's-holder earnings; fail 2 of 3 years → lose Direct Loan eligibility; most
  provisions effective 2027-07-01, some technical provisions 2026-08-31. Tipped-occupation
  programs get delayed consequences (No Tax on Tips data lag).
