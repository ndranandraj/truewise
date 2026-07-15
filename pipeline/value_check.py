"""Value Check, compute the earnings-premium flag per program.

The flagship signal: does a program's typical graduate earn at least as much as a
typical high-school graduate (the federal earnings-premium, "EP", test)? We compare
each program's median earnings to the state and national earnings thresholds
(EARN_THR_STATE / EARN_THR_NAT), and expose a plain debt-to-earnings ratio.

The flag logic lives in ONE place, `build_value_check(con)` runs SQL against the
`fos` table, and the tests exercise that same function on synthetic data, so what
is tested is exactly what ships.

Principles enforced here:
  * Never impute. If earnings or the state threshold is missing -> "insufficient_data".
  * A flag describes the data; it never says "don't attend".
  * The ratio below is a plain median-debt / median-annual-earnings figure, NOT the
    federal amortized debt-to-earnings rate (that needs an amortization schedule;
    a follow-up). It is labeled as such.

Usage (run from the repo root):
    python -m pipeline.value_check
"""

from __future__ import annotations

import datetime as dt

import duckdb

from pipeline.config import ARCHIVE_DIR, DB_PATH, PARQUET_DIR

# Compact columns preserved in the dated FVT/GE Monitor snapshot (diffable, ~1.4 MB).
SNAPSHOT_COLUMNS = [
    "unitid",
    "opeid6",
    "inst_name",
    "state",
    "cip_code",
    "credential_level",
    "credential_desc",
    "earnings",
    "earnings_threshold_state",
    "earnings_threshold_national",
    "earnings_premium_state",
    "fails_ep_state",
    "value_flag",
    "debt_median",
    "debt_to_earnings_ratio",
]

SOURCE_DATASET = "college_scorecard_field_of_study"

VALUE_CHECK_SQL = """
CREATE OR REPLACE TABLE value_check AS
WITH base AS (
    SELECT
        unitid, opeid6, inst_name, state, control,
        cip_code, cip_desc, credential_level, credential_desc,
        completers_count,
        earnings_median_1yr, earnings_median_4yr,
        earnings_threshold_state, earnings_threshold_national,
        debt_median,
        -- Prefer 4-year-after-completion earnings, matching what ED publishes on the
        -- College Scorecard consumer site; fall back to 1-year where 4-year is suppressed.
        COALESCE(earnings_median_4yr, earnings_median_1yr) AS earnings,
        CASE
            WHEN earnings_median_4yr IS NOT NULL THEN '4yr_after_completion'
            WHEN earnings_median_1yr IS NOT NULL THEN '1yr_after_completion'
            ELSE NULL
        END AS earnings_horizon
    FROM fos
)
SELECT
    *,
    (earnings - earnings_threshold_state)    AS earnings_premium_state,
    (earnings - earnings_threshold_national) AS earnings_premium_national,
    CASE WHEN earnings IS NULL OR earnings_threshold_state IS NULL THEN NULL
         ELSE earnings < earnings_threshold_state END       AS fails_ep_state,
    CASE WHEN earnings IS NULL OR earnings_threshold_national IS NULL THEN NULL
         ELSE earnings < earnings_threshold_national END     AS fails_ep_national,
    CASE
        WHEN earnings IS NULL OR earnings_threshold_state IS NULL THEN 'insufficient_data'
        WHEN earnings < earnings_threshold_state THEN 'fails_earnings_premium'
        ELSE 'passes_earnings_premium'
    END AS value_flag,
    CASE WHEN earnings IS NULL OR earnings = 0 OR debt_median IS NULL THEN NULL
         ELSE round(debt_median / earnings, 3) END           AS debt_to_earnings_ratio,
    '{source}' AS source_dataset
FROM base
"""


def build_value_check(con: duckdb.DuckDBPyConnection) -> None:
    """Create the `value_check` table from an existing `fos` table on `con`."""
    con.execute(VALUE_CHECK_SQL.format(source=SOURCE_DATASET))


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    if not con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'fos'"
    ).fetchone()[0]:
        raise SystemExit("No `fos` table. Run `python pipeline/build_spine.py` first.")

    build_value_check(con)

    total = con.execute("SELECT count(*) FROM value_check").fetchone()[0]
    print(f"value_check rows: {total:,}")
    print("  by flag:")
    for flag, n in con.execute(
        "SELECT value_flag, count(*) FROM value_check GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall():
        print(f"    {flag:24s} {n:>8,}  ({100 * n / total:.1f}%)")

    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    out = PARQUET_DIR / "value_check.parquet"
    con.execute(f"COPY value_check TO '{out}' (FORMAT PARQUET)")
    print(f"\nWrote -> {out}")

    # Dated FVT/GE Monitor snapshot, the compact, committed, diffable record.
    snap_dir = ARCHIVE_DIR / dt.date.today().isoformat()
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap = snap_dir / "value_check_snapshot.parquet"
    con.execute(
        f"COPY (SELECT {', '.join(SNAPSHOT_COLUMNS)} FROM value_check) "
        f"TO '{snap}' (FORMAT PARQUET, COMPRESSION zstd)"
    )
    print(f"Monitor snapshot -> {snap}")
    con.close()


if __name__ == "__main__":
    main()
