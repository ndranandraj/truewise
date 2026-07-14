# Methodology — Value Check

_How Truewise computes whether a college program's graduates typically out-earn a
high-school graduate (the federal "earnings-premium" test). Version 0.1, 2026-07._

## Sources

Everything comes from two public U.S. Department of Education College Scorecard bulk
files (most recent release, dated 2026-06-10), joined on the IPEDS **UNITID**:

- **Field-of-Study file** — one row per school × 4-digit CIP × credential level.
  Provides median earnings after completion (`EARN_MDN_1YR`, `EARN_MDN_4YR`), median
  debt at graduation (`DEBT_ALL_STGP_EVAL_MDN`), and the count of graduates out-earning
  the threshold (`EARN_GT_THRESHOLD_1YR`) over the working-not-enrolled count
  (`EARN_COUNT_WNE_1YR`).
- **Institution file** — provides the earnings **thresholds** (`EARN_THR_STATE`,
  `EARN_THR_NAT`): the median earnings of a working adult (25–34) with only a
  high-school diploma, by state and nationally. These are institution-level (based on
  the school's state), so they are joined onto each program.

## The earnings-premium flag

For each program we take median earnings 1 year after completion (falling back to the
4-year figure) and compare it to the state threshold:

- **`passes_earnings_premium`** — median earnings ≥ the state HS-grad threshold.
- **`fails_earnings_premium`** — median earnings < the state HS-grad threshold.
- **`insufficient_data`** — earnings suppressed (small cohort) or no threshold available.

We also report the **earnings premium in dollars** (median − threshold), state and
national; a **companion share** (`share_earning_above_hs_grad` = graduates out-earning
the threshold ÷ working graduates); and a plain **debt-to-earnings ratio** (median debt
÷ median annual earnings — *not* the federal amortized D/E rate, which needs an
amortization schedule and is a planned addition).

## Principles

- **Never impute.** Suppressed values (`PS`, `NA`) become NULL and render as
  "insufficient data" — never guessed.
- **Every figure carries its source and cohort.** Earnings reflect the recent past;
  we frame them as "graduates typically earned," never a promise.
- **A flag describes the data.** It never tells anyone whether to attend a program.

## Coverage (2026-06-10 data)

Of 227,980 programs, **60,202 (26%) have sufficient data** for a determination; the rest
have earnings suppressed by ED for privacy (small cohorts). Among the decided programs,
**29% fail the earnings-premium test** — their graduates typically earn less than a
typical high-school graduate. 94.8% of programs matched an institution-level threshold.

## Validation

- **By construction**, the flag uses ED's own published median earnings and thresholds,
  so it reproduces the federal earnings-premium comparison directly.
- **Independent cross-check:** compared against ED's separate count of graduates
  out-earning the threshold (`EARN_GT_THRESHOLD`), our median-based flag agrees on
  **86.7%** of comparable programs. Disagreements cluster at the boundary (median ≈
  threshold), where ED's two underlying counts use slightly different bases.
- Unit tests exercise the exact flag SQL on synthetic edge cases (suppressed earnings,
  missing threshold, division-by-zero, state-vs-national, share).

## Known limitations

- The companion share can slightly exceed 100% because ED's "count above threshold" and
  "working, not enrolled" counts use marginally different bases; it is a companion signal,
  not the test itself.
- The debt-to-earnings ratio here is a plain ratio, not the amortized federal D/E rate.
- Earnings cohorts predate the current year; figures describe past graduates.
