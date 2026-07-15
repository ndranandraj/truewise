# Truewise pipeline

Builds the Value Check spine from College Scorecard **Field-of-Study** data.

## Why two kinds of steps

- **`download`** needs open internet to pull the bulk file from ed.gov. Run it on
  your Mac or in GitHub Actions.
- **`build_spine`, `value_check`, `pytest`** run on local files only (no network),
  so they work anywhere once the CSV is present.

## Run it (from the repo root)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python -m pipeline.download       # -> archive/fvt/<date>/ snapshot + data/raw/*.csv
python -m pipeline.build_spine    # -> data/truewise.duckdb + data/parquet/fos.parquet
python -m pipeline.value_check    # -> data/parquet/value_check.parquet
```

Or with make: `make data && make spine && make flags` (or `make all`).

## What each step produces

| Step | Output | Notes |
|------|--------|-------|
| `download` | `archive/fvt/<YYYY-MM-DD>/…zip` + `SOURCE.txt`, `data/raw/*.csv` | The dated zip is **snapshot #1 of the FVT/GE Monitor**, a copy ED does not preserve. |
| `build_spine` | `fos` table + `data/parquet/fos.parquet` | Loads losslessly, prints the resolved field mapping, cleans suppressed values to NULL. |
| `value_check` | `value_check` table + `data/parquet/value_check.parquet` | Earnings-premium flag per program. |

`data/` is gitignored; `archive/fvt/` is committed (the snapshots are the artifact).

## The Value Check flag

Per program (school × 4-digit CIP × credential):

- `value_flag`: `passes_earnings_premium`, `fails_earnings_premium`, or `insufficient_data`.
- `fails_ep_state` / `fails_ep_national`: earnings below the state / national HS-grad
  earnings threshold (`EARN_THR_STATE` / `EARN_THR_NAT`).
- `earnings_premium_state` / `_national`: median earnings minus the threshold (dollars).
- `debt_to_earnings_ratio`: plain median-debt / median-annual-earnings. **Not** the
  federal amortized D/E rate (that needs an amortization schedule, a follow-up).

Principles: never impute suppressed values (render "insufficient data"); every figure
carries its source; a flag describes the data, it never says "don't attend".

## Field names

Bulk-CSV column names occasionally change between releases, so `config.py` lists
**candidate** names per field and `build_spine` picks the first present, failing loudly
if a required one is missing. After the first `download`, check the mapping it prints
and adjust `FOS_FIELD_CANDIDATES` if anything shows `(not found)`.
