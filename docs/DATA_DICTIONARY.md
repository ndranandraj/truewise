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

See [METHODOLOGY.md](METHODOLOGY.md) for how the flag is computed and [AUDIT.md](AUDIT.md)
for verification against ED's live site.
