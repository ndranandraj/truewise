# Data dictionary, Truewise Value Check dataset

One row per **institution × 4-digit CIP code × credential level**. Derived from the U.S.
Department of Education College Scorecard (Field-of-Study + Institution files). Suppressed
small-cohort values are `null` (never imputed). Distributed as `value_check.parquet` in the
`truewise-data` package and on the releases page. License: **CC-BY-4.0**.

| column | type | description |
|---|---|---|
| `unitid` | string | IPEDS UnitID, the institution identifier. |
| `opeid6` | string | 6-digit OPEID (Office of Postsecondary Education ID). |
| `inst_name` | string | Institution name. |
| `state` | string | Institution's state (2-letter). |
| `control` | string | Public / Private nonprofit / Private for-profit / Foreign. |
| `cip_code` | string | 4-digit CIP code (field of study). |
| `cip_desc` | string | Field-of-study name. |
| `credential_level` | string | Credential level code (Scorecard `CREDLEV`). |
| `credential_desc` | string | Credential name (e.g. Bachelor's Degree). |
| `completers_count` | number | Award count for the program (IPEDS). May be null. |
| `earnings` | number | Median earnings 4 years after completion, USD (falls back to 1-year where 4-year is suppressed). Mirrors ED's published figure. |
| `earnings_horizon` | string | `4yr_after_completion` or `1yr_after_completion`, which measure `earnings` used. |
| `earnings_threshold_state` | number | Typical high-school-graduate earnings in the school's state, USD (the earnings-premium benchmark). |
| `earnings_threshold_national` | number | Typical high-school-graduate earnings nationally, USD. |
| `earnings_premium_state` | number | `earnings − earnings_threshold_state` (negative = below a HS grad). |
| `earnings_premium_national` | number | `earnings − earnings_threshold_national`. |
| `fails_ep_state` | boolean | True if earnings are below the state threshold; null if undetermined. |
| `value_flag` | string | `passes_earnings_premium` / `fails_earnings_premium` / `insufficient_data`. |
| `debt_median` | number | Median debt at graduation for the program, USD. |
| `debt_to_earnings_ratio` | number | `debt_median ÷ earnings`. A plain ratio, **not** the federal amortized debt-to-earnings rate. |
| `debt_payback_years` | number | Years for the yearly earnings premium over a HS grad to recoup the borrowed debt: `debt_median ÷ earnings_premium_state`. Null where there is no premium to recoup (fails the earnings-premium test or missing data) or no debt, so it is never negative. |

## `institutions.parquet`: completion and credential columns

One row per institution, from ED's Institution file. The table above describes
`value_check.parquet`; these are the institution columns behind the profile's "About the college"
and "Colleges to compare" sections. The last three were added in November 2026.

| Column | Type | Meaning |
|---|---|---|
| `completion_rate` | number | Share of first-time, full-time students who finished within 150% of the normal time for their program (`C150_4`, or `C150_L4` for less-than-four-year institutions). A fraction, 0 to 1. Null where ED publishes none, and where ED publishes a literal 0 for an institution with no such students. |
| `completion_cohort` | integer | The number of students `completion_rate` rests on: the adjusted cohort (`D150_4` or `D150_L4`, matching the rate used). Null exactly where the rate is null. 923 of the 5,058 rates in the 2026-06-10 release rest on fewer than 30 students. |
| `completion_basis` | string | `four_year` or `less_than_four_year`: which of ED's two rates applies. It decides which entering year the rate describes. Null exactly where the rate is null. |
| `predominant_degree` | integer | ED's predominant undergraduate credential, from awards conferred (`PREDDEG`): 0 not classified, 1 certificate, 2 associate's, 3 bachelor's, 4 entirely graduate. |

Each figure describes a different year, and the years move with each College Scorecard release.
They are recorded per release in `pipeline/profile_basics.py` (`YEARS`), from ED's data dictionary.

See [METHODOLOGY.md](METHODOLOGY.md) for how the flag is computed and [AUDIT.md](AUDIT.md)
for verification against ED's live site.
