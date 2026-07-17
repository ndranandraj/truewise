# Truewise

Open, honest US education data for students and families. Truewise turns scattered public
federal data into clear answers: does a college program's graduates out-earn a high-school
graduate, what do families actually pay, what does a major lead to, and what do public high
schools offer. Live at **[truewise.dev](https://truewise.dev)**. Not affiliated with the
U.S. Department of Education.

## The headline finding

Of the college programs with reported earnings, about **1 in 11 (9%)** leave graduates
earning less than a typical high-school graduate, measured up to four years after finishing,
using the Department of Education's own College Scorecard figures. Only about **26% of
programs** have earnings data (the rest are privacy-suppressed by ED for small cohorts); we
compute the rate on the reported set and say so. Among cosmetology programs specifically,
**96%** fall short.

Full derivation, denominators, and caveats: [truewise.dev/methodology](https://truewise.dev/methodology/)
and [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md). We also publish the audit that caught our own
one-year-vs-four-year earnings bug: [`docs/AUDIT.md`](docs/AUDIT.md).

## What's live

- **Value Check**, per-program earnings vs the state high-school-graduate benchmark, with debt.
- **Affordability**, net price by family-income bracket, on every school profile.
- **ROI**, years for the earnings premium to recoup typical debt.
- **Mobility**, Pell share, completion, and earnings outcomes with a transparent hidden-gem rule.
- **Careers** ([/careers](https://truewise.dev/careers/)), what a major pays plus BLS occupation
  pay and outlook.
- **High schools** ([/k12](https://truewise.dev/k12/)), advanced-course access, staffing, and
  state report cards, from the Civil Rights Data Collection.

## Reproduce the numbers

The joined dataset is committed under `published/` and the headline script is
`analysis/summary.py`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data/parquet && cp published/value_check.parquet data/parquet/   # committed build source
python -m analysis.summary                                                # prints + writes the headline numbers
python -m analysis.validate                                               # data-quality gate
pytest                                                                    # unit + integration tests
```

To rebuild from the raw Scorecard files (needs network to download them), see `pipeline/README.md`
and the `Makefile` targets (`make data && make spine && make flags`).

## Use the dataset

The cleaned, joined program-level dataset is CC-BY-4.0. It lives in
[`packages/truewise-data/`](packages/truewise-data/) and `published/`. Column definitions are in
[`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md). Until the PyPI release, install from source:

```bash
pip install ./packages/truewise-data
```
```python
import truewise_data as tw
df = tw.load_value_check(decided_only=True)   # earnings vs a HS-grad benchmark, per program
```

## Data sources

- U.S. Dept. of Education **College Scorecard** (Field-of-Study + Institution), release 2026-06-10.
- **NCES CIP-to-SOC crosswalk**, **BLS OEWS** (May 2023) and **Employment Projections** (2023-33).
- **Civil Rights Data Collection (CRDC)**, 2020-21.

## License

Code is MIT (see `LICENSE`). The published dataset is CC-BY-4.0.
