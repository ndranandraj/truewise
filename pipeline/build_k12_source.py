"""Extract a compact high-school table from the Civil Rights Data Collection (CRDC).

The CRDC ships one big CSV per topic (~16-36 MB each) with cryptic column names and reserved
negative codes for suppressed / not-applicable values. This step, which runs where the CSVs
live (your Mac, not the restricted build sandbox), reads the five files we need, keeps only
high schools, and writes a small per-school build-source: data/parquet/k12.parquet.

Inputs (place the CRDC "School" CSVs in data/raw/crdc/, or pass the folder as argv[1]):
  * School Characteristics.csv  -> identity + grade span (to keep high schools)
  * Enrollment.csv              -> total enrollment (the participation denominator)
  * Advanced Placement.csv      -> offers-AP flag, # AP courses, AP enrollment
  * Calculus.csv / Physics.csv / Chemistry.csv / Computer Science.csv -> offer flag + enrollment
  * Dual Enrollment.csv / International Baccalaureate.csv / Gifted and Talented.csv -> offer + enrollment

Every count uses CRDC's convention that a negative value means suppressed / not applicable,
so negatives are treated as "no data", never as zero data. Offering flags come from the
survey's own indicator/among-classes fields.

Usage (run from the repo root, on a machine that has the CRDC CSVs):
    python -m pipeline.build_k12_source [path/to/CRDC/School]
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from pipeline.config import PARQUET_DIR, RAW_DIR

# The seven CRDC race/ethnicity codes; each appears with a _M and _F suffix.
RACES = ("HI", "AM", "AS", "HP", "BL", "WH", "TR")


def _pos(col: str) -> str:
    """Numeric value when non-negative, else 0 (negatives are CRDC 'no data' codes)."""
    return f"CASE WHEN TRY_CAST({col} AS DOUBLE) >= 0 THEN TRY_CAST({col} AS DOUBLE) ELSE 0 END"


def _posn(col: str) -> str:
    """Numeric value when non-negative, else NULL (for counts we want to distinguish)."""
    return f"CASE WHEN TRY_CAST({col} AS DOUBLE) >= 0 THEN TRY_CAST({col} AS DOUBLE) END"


def _sum_races(alias: str, prefix: str, races=RACES) -> str:
    """Sum a metric across the given race codes and both sexes.

    Summing the race-by-sex components (not the TOT_* columns) is deliberate: CRDC sometimes
    suppresses a total (e.g. TOT_ENR_F = -11) while the underlying race cells are present, so
    the components give a complete count where the total would silently undercount.
    """
    return " + ".join(_pos(f"{alias}.{prefix}_{r}_{s}") for r in races for s in ("M", "F"))


def _find(folder: Path, name: str) -> str:
    hits = sorted(folder.glob(f"{name}*.csv"))
    if not hits:
        raise SystemExit(
            f"Missing '{name}*.csv' in {folder}. Point me at the CRDC 'School' folder."
        )
    return str(hits[-1])


def build(con: duckdb.DuckDBPyConnection, folder: Path) -> None:
    def view(name, file):
        path = _find(folder, file).replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_csv('{path}', all_varchar=true, header=true, sample_size=-1)"
        )

    view("chars", "School Characteristics")
    view("enr", "Enrollment")
    view("ap", "Advanced Placement")
    view("calc", "Calculus")
    view("phys", "Physics")
    view("cs", "Computer Science")
    view("chem", "Chemistry")
    view("dual", "Dual Enrollment")
    view("ib", "International Baccalaureate")
    view("gt", "Gifted and Talented")
    view("ss", "School Support")

    con.execute(
        f"""
        CREATE OR REPLACE TABLE k12 AS
        SELECT
            c.COMBOKEY                                   AS combokey,
            c.LEA_STATE                                  AS state,
            c.SCH_NAME                                   AS name,
            c.LEA_NAME                                   AS district,
            (upper(c.SCH_STATUS_CHARTER) = 'YES')        AS charter,
            (upper(c.SCH_STATUS_MAGNET) = 'YES')         AS magnet,
            {_sum_races("e", "SCH_ENR")}                          AS enroll_total,
            (upper(a.SCH_APENR_IND) = 'YES')             AS offers_ap,
            {_posn("a.SCH_APCOURSES")}                   AS ap_courses,
            {_sum_races("a", "SCH_APENR")}                        AS ap_enroll,
            ({_pos("m.SCH_MATHCLASSES_CALC")} > 0)       AS offers_calc,
            {_sum_races("m", "SCH_MATHENR_CALC")}                 AS calc_enroll,
            ({_pos("p.SCH_SCICLASSES_PHYS")} > 0)        AS offers_physics,
            {_sum_races("p", "SCH_SCIENR_PHYS")}                  AS phys_enroll,
            ({_pos("cs.SCH_COMPCLASSES_CSCI")} > 0)      AS offers_cs,
            {_sum_races("cs", "SCH_COMPENR_CSCI")}                AS cs_enroll,
            ({_pos("ch.SCH_SCICLASSES_CHEM")} > 0)       AS offers_chem,
            {_sum_races("ch", "SCH_SCIENR_CHEM")}                 AS chem_enroll,
            (upper(d.SCH_DUAL_IND) = 'YES')              AS offers_dual,
            {_sum_races("d", "SCH_DUALENR")}                      AS dual_enroll,
            (upper(ib.SCH_IBENR_IND) = 'YES')            AS offers_ib,
            {_sum_races("ib", "SCH_IBENR")}                       AS ib_enroll,
            (upper(g.SCH_GT_IND) = 'YES')                AS offers_gt,
            {_sum_races("g", "SCH_GTENR")}                        AS gt_enroll,
            -- Support staff (FTE; NULL when the school did not report, so a true 0 is meaningful).
            {_posn("ss.SCH_FTECOUNSELORS")}              AS fte_counselors,
            {_posn("ss.SCH_FTESECURITY_LEO")}            AS fte_police,
            {_posn("ss.SCH_FTESECURITY_GUA")}            AS fte_guards,
            {_posn("ss.SCH_FTETEACH_TOT")}               AS fte_teachers,
            {_posn("ss.SCH_FTETEACH_NOTCERT")}           AS fte_teach_uncert
        FROM chars c
        LEFT JOIN enr  e USING (COMBOKEY)
        LEFT JOIN ap   a USING (COMBOKEY)
        LEFT JOIN calc m USING (COMBOKEY)
        LEFT JOIN phys p USING (COMBOKEY)
        LEFT JOIN cs   cs USING (COMBOKEY)
        LEFT JOIN chem ch USING (COMBOKEY)
        LEFT JOIN dual d USING (COMBOKEY)
        LEFT JOIN ib   ib USING (COMBOKEY)
        LEFT JOIN gt   g USING (COMBOKEY)
        LEFT JOIN ss   ss USING (COMBOKEY)
        -- High schools only: offers any of grades 9-12.
        WHERE upper(c.SCH_GRADE_G09) = 'YES' OR upper(c.SCH_GRADE_G10) = 'YES'
           OR upper(c.SCH_GRADE_G11) = 'YES' OR upper(c.SCH_GRADE_G12) = 'YES'
        """
    )


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else (RAW_DIR / "crdc")
    if not folder.exists():
        raise SystemExit(
            f"CRDC folder {folder} not found. Put the CRDC 'School' CSVs in {RAW_DIR / 'crdc'} "
            "or pass the folder path as an argument."
        )
    con = duckdb.connect()
    build(con, folder)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    out = PARQUET_DIR / "k12.parquet"
    con.execute(f"COPY k12 TO '{out}' (FORMAT PARQUET)")

    n = con.execute("SELECT count(*) FROM k12").fetchone()[0]
    print(f"high schools: {n:,}")
    for label, col in [
        ("AP", "offers_ap"),
        ("calculus", "offers_calc"),
        ("physics", "offers_physics"),
        ("chemistry", "offers_chem"),
        ("computer science", "offers_cs"),
        ("dual enrollment", "offers_dual"),
        ("IB", "offers_ib"),
        ("gifted/talented", "offers_gt"),
    ]:
        k = con.execute(f"SELECT count(*) FILTER (WHERE {col}) FROM k12").fetchone()[0]
        print(f"  offer {label}: {k:,} ({100 * k / n:.0f}%)")
    print("\nSample (largest AP programs):")
    for r in con.execute(
        "SELECT name, state, enroll_total, ap_enroll, ap_courses FROM k12 "
        "WHERE offers_ap ORDER BY ap_enroll DESC LIMIT 3"
    ).fetchall():
        print(f"  {r[0][:34]:34s} {r[1]}  enroll={int(r[2]):,}  AP={int(r[3]):,}  courses={r[4]}")
    print(f"\nwrote -> {out}")


if __name__ == "__main__":
    main()
