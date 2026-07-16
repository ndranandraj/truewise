# Methodology, Value Check

_How Truewise computes whether a college program's graduates typically out-earn a
high-school graduate (the federal "earnings-premium" test). Version 0.1, 2026-07._

## Sources

Everything comes from two public U.S. Department of Education College Scorecard bulk
files (most recent release, dated 2026-06-10), joined on the IPEDS **UNITID**:

- **Field-of-Study file**, one row per school × 4-digit CIP × credential level.
  Provides median earnings after completion (`EARN_MDN_1YR`, `EARN_MDN_4YR`), median
  debt at graduation (`DEBT_ALL_STGP_EVAL_MDN`), and the count of graduates out-earning
  the threshold (`EARN_GT_THRESHOLD_1YR`) over the working-not-enrolled count
  (`EARN_COUNT_WNE_1YR`).
- **Institution file**, provides the earnings **thresholds** (`EARN_THR_STATE`,
  `EARN_THR_NAT`): the median earnings of a working adult (25–34) with only a
  high-school diploma, by state and nationally. These are institution-level (based on
  the school's state), so they are joined onto each program.

## The earnings-premium flag

For each program we take median earnings **4 years after completion**, the same figure the
Department of Education displays on the public College Scorecard site, falling back to the
1-year figure only where the 4-year value is suppressed, and compare it to the state threshold:

- **`passes_earnings_premium`**, median earnings ≥ the state HS-grad threshold.
- **`fails_earnings_premium`**, median earnings < the state HS-grad threshold.
- **`insufficient_data`**, earnings suppressed (small cohort) or no threshold available.

We also report the **earnings premium in dollars** (median − threshold), state and
national, and a plain **debt-to-earnings ratio** (median debt ÷ median annual earnings , 
*not* the federal amortized D/E rate, which needs an amortization schedule and is a
planned addition).

## Principles

- **Never impute.** Suppressed values (`PS`, `NA`) become NULL and render as
  "insufficient data", never guessed.
- **Every figure carries its source and cohort.** Earnings reflect the recent past;
  we frame them as "graduates typically earned," never a promise.
- **A flag describes the data.** It never tells anyone whether to attend a program.

## Coverage (2026-06-10 data)

Of 227,980 programs, **60,202 (26%) have sufficient data** for a determination; the rest
have earnings suppressed by ED for privacy (small cohorts). Among the decided programs,
**9% fail the earnings-premium test**, their graduates typically earn less than a
typical high-school graduate even four years after finishing. 94.8% of programs matched
an institution-level threshold.

## Validation

- **By construction**, the flag uses ED's own published median earnings and thresholds,
  so it reproduces the federal earnings-premium comparison directly.
- **Matches ED's public site exactly.** A 20-program audit against the live College
  Scorecard site confirmed our earnings equal ED's displayed figures to the dollar (e.g.
  UCLA Economics $95,440, Psychology $61,050, Sociology $64,692). The audit is what led us
  to use the 4-year earnings measure ED publishes rather than the 1-year figure, see
  [AUDIT.md](AUDIT.md).
- **Independent cross-check:** compared against ED's separate count of graduates
  out-earning the threshold (`EARN_GT_THRESHOLD`), our median-based flag agrees on the
  large majority of comparable programs; disagreements cluster at the boundary
  (median ≈ threshold), where ED's two underlying counts use slightly different bases.
- Unit tests exercise the exact flag SQL on synthetic edge cases (suppressed earnings,
  missing threshold, division-by-zero, state-vs-national, share).

## Affordability (net price by income)

Each school profile also shows **net price by family income bracket**: what students whose
families fall in each of five income ranges ($0 to $30k, $30k to $48k, $48k to $75k, $75k to
$110k, $110k and up) typically paid per year after grants and scholarships. These figures are
College Scorecard's `NPT41`-`NPT45` fields, coalesced across the school's sector (public,
private, program-year). Suppressed brackets show as "not reported," never guessed. Figures
describe past students, not a quote; profiles link each school's own net price calculator for
a personal estimate. The idea of ranking schools by what families at each income level
actually pay was pioneered by [TuitionTracker](https://www.tuitiontracker.org/), which we
credit here; Truewise's contribution is joining it with the earnings-premium view on one page.

## Return on investment (debt payback)

Each profile also shows a **debt payback** for every program: how many years of a program's
**earnings premium over a typical high-school graduate** it would take to recoup the typical
debt its graduates borrowed.

    debt_payback_years = median debt / (median earnings − state HS-grad threshold)

It is deliberately assumption-free: it uses only figures ED already publishes (median debt and
the same earnings and threshold behind the Value Check flag), so there is no earnings-growth or
discount-rate modeling. It is **null** whenever there is no premium to recoup (a program that
fails the earnings-premium test, or has missing data) or no debt to pay off, so it is never
negative or infinite. A program that fails the earnings premium is shown as not paying back on
this measure rather than as a made-up number.

A secondary **whole-degree cost view** appears on undergraduate programs where net price is
available. It divides the school's average net price times a nominal time-to-finish (2 years for
an associate's, 4 for a bachelor's, 1 for an undergraduate certificate) by the same earnings
premium. Unlike debt payback, this counts the full out-of-pocket cost of the degree, not just
borrowed money, and it carries the stated time-to-finish assumption, so it is presented as an
illustration on the site rather than shipped in the dataset.

Both are descriptive summaries of past graduates. They never tell anyone whether to attend.

## Known limitations

- The debt-to-earnings ratio here is a plain ratio, not the amortized federal D/E rate.
- Earnings cohorts predate the current year; figures describe past graduates.
