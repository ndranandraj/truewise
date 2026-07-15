# Value Check, accuracy audit

_2026-07-14. Verifying Truewise's Value Check numbers against the Department of
Education's own published figures on the live College Scorecard site._

## Method

We drew a 20-program sample across seven well-known universities (Baylor, Florida,
Michigan, Ohio State, Penn State, UCLA, Georgia Tech), mixing pass and fail cases and
several fields of study, and compared each program's earnings and pass/fail verdict to
what ED publishes at `collegescorecard.ed.gov`.

## What the audit found

ED's public site displays **median earnings measured four years after completion**.
Truewise's first version used the **one-year** figure. Because one-year earnings are
much lower (fresh graduates) than the ~$36k earnings threshold (which represents an
established high-school worker aged 25–34), the one-year measure **overstated failures**.

The choice swings the headline dramatically:

| Earnings measure | Programs failing the earnings-premium test | Cosmetology |
|---|---|---|
| 1-year (original) | 33% of decided | 97% |
| **4-year (ED's published figure)** | **9% of decided** | **86%** |

We switched Value Check to the 4-year measure to mirror exactly what ED publishes.

## Verification (post-fix)

Truewise's earnings now equal ED's displayed figures to the dollar. Spot-checks against
the live site:

| Program (UCLA, Bachelor's) | ED site | Truewise | Match |
|---|---|---|---|
| Economics | $95,440 | $95,440 | ✓ |
| Psychology, General | $61,050 | $61,050 | ✓ |
| Sociology | $64,692 | $64,692 | ✓ |

UCLA Psychology and Sociology now correctly **pass** (their 4-year earnings exceed the
threshold), where the 1-year measure had wrongly flagged them as failing. Every Value
Check figure derives from the same College Scorecard column ED displays, so values match
the public site by construction.

## Outcome

- Earnings measure corrected to 4-year (matches ED's public site).
- Headline fail rate: **9% of programs with sufficient data** (was overstated at 33%).
- The low-value-certificate story holds: cosmetology programs still fail at **86%**.
- Methodology updated ([METHODOLOGY.md](METHODOLOGY.md)); companion "share out-earning a
  HS grad" metric switched to the same 4-year horizon for consistency.
