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

## Row order

A join with no `ORDER BY` returns rows in an order that changes with the DuckDB version and the
thread count, which moved checksums with no change in the data. So every parquet a refresh writes
is sorted on a key that identifies one row. `sorted_parquet.py` does this for most of them and stops
the refresh if the key repeats; a test fails on any parquet writer with no `ORDER BY`.

| File | Key |
|------|-----|
| `fos`, `value_check`, the monitor snapshot, the package copy | `unitid, opeid6, cip_code, credential_level` |
| `institutions`, `main_campus` | `unitid` |
| `k12` | `combokey` |
| `careers_demand` | `cip_code` |
| `fvtge_reporting` | `opeid6` |

From the same raw files, any DuckDB version and thread count now write the same rows in the same
order (checked on 1.5.6 and 2.0.0, at 8 threads and 1). Bytes match within one version; another
version records itself in the file, so its bytes differ.

**The first refresh after this change.** `published/` was left in the old order on purpose, so the
new order lands with real data rather than alone. Even with unchanged raw files that refresh shows:

- A new checksum for every parquet it copies, and a new row order in `value_check`, `institutions`
  and `k12`, and in the package copy. The rows themselves are the same.
- A new snapshot whose checksum differs from the July one, so `check_diff_readiness` counts two
  distinct snapshots whatever the data did. Read the diff itself.
- `monitor_diff` listing 21,404 earnings revisions that did not happen. It joins on UNITID, CIP and
  credential level, which repeat under UNITID `NA`, so unrelated rows pair up. Real programs print
  first, but the count is inflated until that join is fixed.
- The Connecticut and Louisiana best-value lists swapping tied rows, unless the tie-order fix for
  those lists has landed first. Nothing else under `site/` moved (one thread, 13,472 files).

## The Value Check flag

Per program (school × 4-digit CIP × credential):

- `value_flag`: `passes_earnings_premium`, `fails_earnings_premium`, or `insufficient_data`.
- `fails_ep_state` / `fails_ep_national`: earnings below the state / national HS-grad
  earnings threshold (`EARN_THR_STATE` / `EARN_THR_NAT`).
- `earnings_premium_state` / `_national`: median earnings minus the threshold (dollars).
- `debt_to_earnings_ratio`: plain median-debt / median-annual-earnings. **Not** the
  federal amortized D/E rate (that needs an amortization schedule, a follow-up).

Principles: never impute suppressed values (render "not published", or "not assessed" where no comparison can be made); every figure
carries its source; a flag describes the data, it never says "don't attend".

## Field names

Bulk-CSV column names occasionally change between releases, so `config.py` lists
**candidate** names per field and `build_spine` picks the first present, failing loudly
if a required one is missing. After the first `download`, check the mapping it prints
and adjust `FOS_FIELD_CANDIDATES` if anything shows `(not found)`.
