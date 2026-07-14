# Truewise — Product Brief

_One page. What Truewise is, who it serves, and what ships. Written 2026-07-13 (Iteration 0)._

## Mission

Turn scattered US federal education data into clear, honest guidance for students and
families. Replace the scary or hidden number (the sticker price, the anecdote, the unclaimed
aid) with the real one, drawn straight from public data. The framing is positive and
opportunity-opening, not problem-cataloguing.

## Who it serves

- **Students and families** deciding where to apply and what to study, who need the honest
  number in plain language.
- **Researchers and journalists** who want a clean, documented, openly licensed dataset and a
  reproducible pipeline to build on, rather than another walled comparison site.

Truewise is open data infrastructure that others build on. The website is the demo layer.

## What makes it different

Individual pieces exist separately (HEA Group reports, Georgetown CEW's ROI tool,
TuitionTracker's net-price-by-income, PyScorecard). The open combination has no incumbent:
a mirror of the federal FVT/GE transparency figures, a dated archive of those figures, one
CC-BY joined dataset, a `truewise-data` pip package, and a fully reproducible pipeline.
Positioning is infrastructure, not another consumer site. Where a module overlaps prior art
(for example affordability), that prior art is credited rather than claimed as novel.

## Modules (build order, v2.2)

1. **Value Check** (flagship, first): does a program's graduates typically out-earn a
   high-school graduate, and how does debt compare to earnings? Mirrors the federal Financial
   Value Transparency & Gainful Employment framework, plus a monitor that snapshots and diffs
   ED's live transparency figures each refresh.
2. **Affordability** — net price by family income bracket (credits TuitionTracker).
3. **ROI** — field-of-study earnings vs debt, payback, completion-weighted.
4. **Mobility** — Opportunity Insights, including a hidden-gems view.
5. **Careers** — major-to-career (CIP→SOC), wages, outlook, grad-program ROI.
6. **K-12** — advanced-course access, beating-the-odds schools, FAFSA gaps.

## Principles (non-negotiable)

- Never impute suppressed or missing values; render "insufficient data" instead.
- Every number carries its source and cohort year.
- Earnings and aid are framed as "students like you earned/paid roughly," never a promise.
- A warning describes the data; it never says "don't attend."

## Architecture (one line each)

- **Spine:** DuckDB + Parquet over the major federal education datasets, joined on school IDs
  (UnitID/OPEID for college, NCES for K-12).
- **Hosting:** static-first, precomputed in CI, served from Cloudflare Pages ($0, no cold starts).
- **Automation:** GitHub Actions — annual full rebuild plus monthly FVT snapshot + link check.

## Constraints

Revenue expected ≈ $0; this is a portfolio, skills, and social-impact project. Domain spend
capped ~$50/yr (truewise.dev). One project at a time.

## Success signals (why this exists)

Public, adoptable artifacts with countable adoption: a published CC-BY dataset (with DOIs), a
pip package, a methodology write-up, press coverage, and talks.
