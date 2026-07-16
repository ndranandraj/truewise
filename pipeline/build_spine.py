"""Load Scorecard CSVs into DuckDB and build the joined Value Check spine.

Runs anywhere the extracted CSVs already exist in data/raw/ (no network needed).
It:

  1. loads the Field-of-Study and Institution CSVs losslessly into DuckDB (as text),
  2. resolves each logical field against the real headers (fails loudly on a missing
     required field) and prints the mapping,
  3. builds a typed `fos` table joined to institution-level earnings thresholds on
     UNITID, with suppressed values ('PS'/'NA'/…) coerced to NULL (never imputed),
  4. writes it to Parquet.

Usage (run from the repo root):
    python -m pipeline.build_spine
"""

from __future__ import annotations

import glob

import duckdb

from pipeline.config import (
    DB_PATH,
    FOS_FIELD_CANDIDATES,
    FOS_REQUIRED,
    INST_FIELD_CANDIDATES,
    INST_REQUIRED,
    PARQUET_DIR,
    RAW_DIR,
    SUPPRESSION_SENTINELS,
)


def _find_csv(*needles: str) -> str:
    for needle in needles:
        hits = sorted(glob.glob(str(RAW_DIR / f"*{needle}*.csv")))
        if hits:
            return hits[-1]
    raise SystemExit(
        f"No CSV matching {needles} in {RAW_DIR}. Run `python -m pipeline.download` first "
        "(on a machine with network access)."
    )


def resolve_columns(
    actual_columns: list[str],
    candidates: dict[str, list[str]],
    required: list[str],
) -> dict[str, str]:
    """Map each logical field to the first candidate present; raise if a required one is absent."""
    present = {c.upper(): c for c in actual_columns}
    resolved: dict[str, str] = {}
    for logical, options in candidates.items():
        hit = next((present[o.upper()] for o in options if o.upper() in present), None)
        if hit:
            resolved[logical] = hit
    missing = [r for r in required if r not in resolved]
    if missing:
        raise SystemExit(
            f"Required field(s) had no matching column: {missing}. "
            "Inspect the CSV header and update the candidates in config.py.\n"
            f"Available columns: {sorted(actual_columns)}"
        )
    return resolved


def _sentinel_list() -> str:
    return ", ".join(f"'{s}'" for s in SUPPRESSION_SENTINELS)


def _num(resolved: dict[str, str], logical: str) -> str:
    col = resolved.get(logical)
    if not col:
        return "NULL"
    return (
        f'CASE WHEN trim("{col}") IN ({_sentinel_list()}) THEN NULL '
        f'ELSE TRY_CAST("{col}" AS DOUBLE) END'
    )


def _txt(resolved: dict[str, str], logical: str) -> str:
    col = resolved.get(logical)
    return f'"{col}"' if col else "NULL"


# Average net price and net-price-by-income-bracket come in parallel columns per sector
# (NPT4x_PUB / _PRIV / _PROG / _OTHER); a school populates only its own sector, so we
# COALESCE across them. bracket "" = average; "1".."5" = the five income brackets.
_NPT_VARIANTS = ("PUB", "PRIV", "PROG", "OTHER")


def _net_price(cols: set[str], bracket: str) -> str:
    names = [f"NPT4{bracket}_{v}" for v in _NPT_VARIANTS]
    present = [n for n in names if n in cols]
    if not present:
        return "NULL"
    parts = [
        f'CASE WHEN trim("{n}") IN ({_sentinel_list()}) THEN NULL ELSE TRY_CAST("{n}" AS DOUBLE) END'
        for n in present
    ]
    return "COALESCE(" + ", ".join(parts) + ")"


def _print_mapping(title: str, candidates: dict[str, str], resolved: dict[str, str]) -> None:
    print(f"  {title} field mapping:")
    for logical in candidates:
        print(f"    {logical:28s} -> {resolved.get(logical, '(not found)')}")


def main() -> None:
    fos_csv = _find_csv("Field-of-Study")
    inst_csv = _find_csv("Institution")
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    for tbl, path in (("fos_raw", fos_csv), ("inst_raw", inst_csv)):
        con.execute(
            f"CREATE OR REPLACE TABLE {tbl} AS "
            "SELECT * FROM read_csv(?, all_varchar=true, header=true, sample_size=-1)",
            [path],
        )

    fos_cols = [r[0] for r in con.execute("DESCRIBE fos_raw").fetchall()]
    inst_cols = [r[0] for r in con.execute("DESCRIBE inst_raw").fetchall()]
    fos = resolve_columns(fos_cols, FOS_FIELD_CANDIDATES, FOS_REQUIRED)
    inst = resolve_columns(inst_cols, INST_FIELD_CANDIDATES, INST_REQUIRED)

    print(f"Field-of-Study: {fos_csv}")
    print(f"  rows: {con.execute('SELECT count(*) FROM fos_raw').fetchone()[0]:,}")
    _print_mapping("Field-of-Study", FOS_FIELD_CANDIDATES, fos)
    print(f"Institution: {inst_csv}")
    print(f"  rows: {con.execute('SELECT count(*) FROM inst_raw').fetchone()[0]:,}")
    _print_mapping("Institution", INST_FIELD_CANDIDATES, inst)

    # Institution-level identity + thresholds + net price, one row per school.
    icols = set(inst_cols)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE institutions AS SELECT
            {_txt(inst, "unitid")}                        AS unitid,
            {_txt(inst, "inst_name")}                     AS inst_name,
            {_txt(inst, "city")}                          AS city,
            {_txt(inst, "state")}                         AS state,
            {_txt(inst, "school_url")}                    AS school_url,
            {_num(inst, "enrollment")}                    AS enrollment,
            {_num(inst, "earnings_threshold_state")}      AS earnings_threshold_state,
            {_num(inst, "earnings_threshold_national")}   AS earnings_threshold_national,
            {_num(inst, "pell_share")}                    AS pell_share,
            {_num(inst, "first_gen_share")}               AS first_gen_share,
            COALESCE({_num(inst, "completion_4yr")}, {_num(inst, "completion_l4")}) AS completion_rate,
            {_net_price(icols, "")}                       AS net_price_avg,
            {_net_price(icols, "1")}                      AS net_price_0_30k,
            {_net_price(icols, "2")}                      AS net_price_30_48k,
            {_net_price(icols, "3")}                      AS net_price_48_75k,
            {_net_price(icols, "4")}                      AS net_price_75_110k,
            {_net_price(icols, "5")}                      AS net_price_110k_plus
        FROM inst_raw
        """
    )
    con.execute(f"COPY institutions TO '{PARQUET_DIR / 'institutions.parquet'}' (FORMAT PARQUET)")

    # Program-level table joined to its institution's thresholds by UNITID.
    con.execute(
        f"""
        CREATE OR REPLACE TABLE fos AS
        WITH p AS (
            SELECT
                {_txt(fos, "unitid")}            AS unitid,
                {_txt(fos, "opeid6")}            AS opeid6,
                {_txt(fos, "inst_name")}         AS inst_name,
                {_txt(fos, "control")}           AS control,
                {_txt(fos, "cip_code")}          AS cip_code,
                {_txt(fos, "cip_desc")}          AS cip_desc,
                {_txt(fos, "credential_level")}  AS credential_level,
                {_txt(fos, "credential_desc")}   AS credential_desc,
                {_num(fos, "completers_count")}      AS completers_count,
                {_num(fos, "earnings_median_1yr")}   AS earnings_median_1yr,
                {_num(fos, "earnings_median_4yr")}   AS earnings_median_4yr,
                {_num(fos, "debt_median")}           AS debt_median
            FROM fos_raw
        )
        SELECT
            p.*,
            i.state                        AS state,
            i.earnings_threshold_state     AS earnings_threshold_state,
            i.earnings_threshold_national  AS earnings_threshold_national
        FROM p LEFT JOIN institutions i USING (unitid)
        """
    )

    n = con.execute("SELECT count(*) FROM fos").fetchone()[0]
    matched = con.execute(
        "SELECT count(*) FROM fos WHERE earnings_threshold_state IS NOT NULL"
    ).fetchone()[0]
    print(
        f"\n  programs: {n:,}  |  with a state threshold joined: {matched:,} ({100 * matched / n:.1f}%)"
    )
    out = PARQUET_DIR / "fos.parquet"
    con.execute(f"COPY fos TO '{out}' (FORMAT PARQUET)")
    print(f"  wrote -> {out}")
    con.close()
    print("Next: python -m pipeline.value_check")


if __name__ == "__main__":
    main()
