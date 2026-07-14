"""Load the Field-of-Study CSV into DuckDB and resolve the Truewise field mapping.

Runs anywhere the extracted CSV already exists in data/raw/ (no network needed),
so it works inside the sandbox once the file is present. It:

  1. loads the raw CSV losslessly into DuckDB (every column, as text),
  2. resolves each logical field (config.FOS_FIELD_CANDIDATES) against the real
     header and prints a mapping report — failing loudly if a required concept
     has no matching column,
  3. writes a typed, cleaned `fos` table (suppressed sentinels -> NULL) to Parquet.

Usage (run from the repo root):
    python -m pipeline.build_spine
"""

from __future__ import annotations

import glob

import duckdb

from pipeline.config import (
    DB_PATH,
    FOS_FIELD_CANDIDATES,
    PARQUET_DIR,
    RAW_DIR,
    SUPPRESSION_SENTINELS,
)

REQUIRED = [
    "unitid",
    "cip_code",
    "credential_level",
    "earnings_threshold_state",
    "earnings_threshold_national",
]


def _find_csv() -> str:
    matches = sorted(glob.glob(str(RAW_DIR / "*Field-of-Study*.csv"))) or sorted(
        glob.glob(str(RAW_DIR / "*.csv"))
    )
    if not matches:
        raise SystemExit(
            f"No CSV in {RAW_DIR}. Run `python -m pipeline.download` first "
            "(on a machine with network access)."
        )
    return matches[-1]


def resolve_columns(actual_columns: list[str]) -> dict[str, str]:
    """Map each logical field to the first candidate present in the file."""
    present = {c.upper(): c for c in actual_columns}
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for logical, candidates in FOS_FIELD_CANDIDATES.items():
        hit = next((present[c.upper()] for c in candidates if c.upper() in present), None)
        if hit:
            resolved[logical] = hit
        elif logical in REQUIRED:
            missing.append(logical)
    if missing:
        raise SystemExit(
            "Required field(s) had no matching column in the data: "
            f"{missing}. Inspect the CSV header and update FOS_FIELD_CANDIDATES.\n"
            f"Available columns: {sorted(actual_columns)}"
        )
    return resolved


def main() -> None:
    csv_path = _find_csv()
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    # Load losslessly as text so no value is coerced/lost on the way in.
    con.execute(
        "CREATE OR REPLACE TABLE fos_raw AS "
        "SELECT * FROM read_csv(?, all_varchar=true, header=true, sample_size=-1)",
        [csv_path],
    )
    actual_columns = [r[0] for r in con.execute("DESCRIBE fos_raw").fetchall()]
    resolved = resolve_columns(actual_columns)

    print(f"Loaded {csv_path}")
    print(f"  rows: {con.execute('SELECT count(*) FROM fos_raw').fetchone()[0]:,}")
    print(f"  columns: {len(actual_columns)}")
    print("  resolved field mapping:")
    for logical in FOS_FIELD_CANDIDATES:
        print(f"    {logical:28s} -> {resolved.get(logical, '(not found)')}")

    # Build a typed, cleaned `fos` table. Suppressed sentinels -> NULL (never imputed).
    def num(logical: str) -> str:
        col = resolved.get(logical)
        if not col:
            return "NULL"
        sentinels = ", ".join(f"'{s}'" for s in SUPPRESSION_SENTINELS)
        return (
            f'CASE WHEN trim("{col}") IN ({sentinels}) THEN NULL '
            f'ELSE TRY_CAST("{col}" AS DOUBLE) END'
        )

    def txt(logical: str) -> str:
        col = resolved.get(logical)
        return f'"{col}"' if col else "NULL"

    con.execute(
        f"""
        CREATE OR REPLACE TABLE fos AS SELECT
            {txt("unitid")}                    AS unitid,
            {txt("opeid6")}                    AS opeid6,
            {txt("inst_name")}                 AS inst_name,
            {txt("state")}                     AS state,
            {txt("control")}                   AS control,
            {txt("cip_code")}                  AS cip_code,
            {txt("cip_desc")}                  AS cip_desc,
            {txt("credential_level")}          AS credential_level,
            {txt("credential_desc")}           AS credential_desc,
            {num("completers_count")}          AS completers_count,
            {num("earnings_median_1yr")}       AS earnings_median_1yr,
            {num("earnings_median_4yr")}       AS earnings_median_4yr,
            {num("earnings_threshold_state")}  AS earnings_threshold_state,
            {num("earnings_threshold_national")} AS earnings_threshold_national,
            {num("debt_median")}               AS debt_median
        FROM fos_raw
        """
    )
    n = con.execute("SELECT count(*) FROM fos").fetchone()[0]
    out = PARQUET_DIR / "fos.parquet"
    con.execute(f"COPY fos TO '{out}' (FORMAT PARQUET)")
    print(f"\nWrote {n:,} rows -> {out}")
    con.close()
    print("Next: python -m pipeline.value_check")


if __name__ == "__main__":
    main()
