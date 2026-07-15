# Data Sources Reference

All datasets are public, free, and bulk-downloadable. Join everything on the keys below.
Verify URLs and field names against current docs when you build (federal sites reorganize).

## Join keys
- Colleges: **IPEDS UnitID** (a.k.a. UNITID) and **OPEID** (8-digit) / OPEID6 (6-digit).
- K-12 schools/districts: **NCES school ID** and **NCES LEA/district ID**.
- Geography: **FIPS** (state+county), ZIP, state.

## College datasets

### College Scorecard (primary source for the college modules)
- Data home: https://collegescorecard.ed.gov/data/
- API docs: https://collegescorecard.ed.gov/data/api-documentation/
- API key (free): https://api.data.gov/signup/  (rate limit 1,000 req/IP/hour)
- Data dictionary + field-of-study docs linked from the data home page.
- Last refreshed: 2026-06-10. Institution files cover 1996-97 → 2025-26.
- Two access routes: **bulk download** (full CSV, no rate limit, use this for the pipeline)
  and the **API** (JSON, needs key, use for spot lookups).
- Grain: institution-level (one row per school, ~6,500 rows, ~3,000 fields) AND
  field-of-study level (school × 4-digit CIP × credential; earnings + debt).

Key fields (institution-level):
- Net price by family income bracket: `NPT4_PUB` / `NPT4_PRIV` and `NPT41..NPT45` variants.
  Brackets: $0–30k, $30,001–48k, $48,001–75k, $75,001–110k, $110k+.
- Cost/tuition: `TUITIONFEE_IN`, `TUITIONFEE_OUT`, `COSTT4_A`.
- Completion: `C150_4`, `C150_L4`; retention `RET_FT4`.
- Debt: median debt fields (e.g., `GRAD_DEBT_MDN`, `DEBT_MDN`).
- Earnings + earnings premium: fields comparing completer earnings to a HS grad
  (national and within-state), the basis for the **Value Check** module. Also
  field-of-study national median earnings. Confirm exact field names in the current
  data dictionary (these were added/expanded in the 2025–2026 updates).
- Pell / aid: `PCTPELL`, `PCTFLOAN`.

Field-of-study file grain: institution × 4-digit CIP code × credential level; includes
cumulative debt at graduation and earnings ~1 year after completion. Note: values are
**suppressed** (blank) for small cohorts, handle as "insufficient data," never impute.

### IPEDS (Integrated Postsecondary Education Data System)
- https://nces.ed.gov/ipeds/use-the-data
- Enrollment, admissions, transfer-out counts, finance, program (CIP) offerings.
- Join on UnitID. Many small survey files; pull only what you need.

### Federal Student Aid (FSA)
- https://studentaid.gov/data-center/
- FAFSA completion (incl. by high school), loan volumes, cohort default / repayment.
- Join colleges on OPEID; FAFSA-by-HS joins K-12 on NCES ID.

### Opportunity Insights (college social mobility)
- https://opportunityinsights.org/data/
- Mobility Report Cards: fraction of students moving from bottom income quintile to top, etc.
- Static research releases (older cohorts, label the years). Join on UnitID / super-OPEID.

## K-12 datasets

### NCES Common Core of Data (CCD)
- https://nces.ed.gov/ccd/
- Directory of ~100k public schools + ~18k districts, enrollment, staffing. Join on NCES ID.

### Civil Rights Data Collection (CRDC)
- https://civilrightsdata.ed.gov/
- Advanced-course access (AP, calculus, physics), dual enrollment, discipline. ~34 MB
  zipped per collection year. Join on NCES ID.

### SEDA (Stanford Education Data Archive)
- https://edopportunity.org/  (data download links on site)
- K-12 achievement + growth, comparable across districts. Join on NCES ID.

## Career / labor datasets
- BLS employment projections & wages: https://www.bls.gov/emp/ and https://www.bls.gov/oes/
- O*NET: https://www.onetcenter.org/database.html  (skills, occupation detail)
- CIP↔SOC crosswalk (major → occupation): https://nces.ed.gov/ipeds/cipcode/ (crosswalk),
  used to link Scorecard majors to BLS occupations.

## Geography / demographics
- Census ACS: https://www.census.gov/programs-surveys/acs/data.html  (API:
  https://www.census.gov/data/developers/data-sets/acs-5year.html). Pull only needed
  variables, full national tables balloon fast.

## Notes
- Earnings/aid data reflect the recent past (cohorts from several years ago). Always label
  cohort years and frame numbers as "students like you paid/earned roughly," not a promise.
- The most precise per-student number comes from each school's own federally-required
  Net Price Calculator, link users there for a personal estimate after they find matches.
