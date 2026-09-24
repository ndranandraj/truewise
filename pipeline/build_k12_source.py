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


# Course-offering flags are TRI-STATE: TRUE (offered), FALSE (reported none), NULL (not reported).
# CRDC marks non-response with negative sentinels (-9 "did not report", -3 "not applicable") and
# absent join rows. Collapsing those to FALSE would publish "does not offer AP" for a school that
# merely didn't answer, which contradicts the site's "never guessed" promise, so unknown stays NULL
# and is excluded from offer rates and the "offers none of three" count downstream.
def _offer_ind(col: str) -> str:
    """From a Yes/No indicator column: TRUE on 'Yes', FALSE on 'No', NULL otherwise (unknown)."""
    return f"CASE WHEN upper({col}) = 'YES' THEN TRUE WHEN upper({col}) = 'NO' THEN FALSE END"


def _offer_cnt(col: str) -> str:
    """From a class-count column: TRUE when >0, FALSE on an observed 0, NULL on a negative sentinel."""
    return (
        f"CASE WHEN TRY_CAST({col} AS DOUBLE) > 0 THEN TRUE "
        f"WHEN TRY_CAST({col} AS DOUBLE) = 0 THEN FALSE END"
    )


def _sum_races(alias: str, prefix: str, races=RACES, present: frozenset[str] | None = None) -> str:
    """Sum a metric across the given race codes and every published sex category.

    2023-24 added a third category (_X) beside _M and _F. It is included whenever the file has
    the column, so a release that populates it is not silently undercounted. `present` is the
    set of column names in the loaded files; without it only _M and _F are used.

    Summing the race-by-sex components (not the TOT_* columns) is deliberate: CRDC sometimes
    suppresses a total (e.g. TOT_ENR_F = -11) while the underlying race cells are present, so
    the components give a complete count where the total would silently undercount.
    """
    sexes = ("M", "F", "X")
    return " + ".join(
        _pos(f"{alias}.{prefix}_{r}_{s}")
        for r in races
        for s in sexes
        if s != "X" or (present is not None and f"{prefix}_{r}_{s}" in present)
    )


def _find(folder: Path, name: str) -> str:
    hits = sorted(folder.glob(f"{name}*.csv"))
    if not hits:
        raise SystemExit(
            f"Missing '{name}*.csv' in {folder}. Point me at the CRDC 'School' folder."
        )
    return str(hits[-1])


HS_WHERE = (
    "upper(c.SCH_GRADE_G09) = 'YES' OR upper(c.SCH_GRADE_G10) = 'YES' "
    "OR upper(c.SCH_GRADE_G11) = 'YES' OR upper(c.SCH_GRADE_G12) = 'YES'"
)


def _detect_vintage(con: duckdb.DuckDBPyConnection) -> str:
    """Name the CRDC collection from its School Characteristics layout, or refuse.

    2021-22 flags justice facilities in a column called JJ; 2023-24 renamed it SCH_JUST_IND. A
    layout that is neither is a release nobody has checked, so the build stops.
    """
    cols = {r[0] for r in con.execute("DESCRIBE chars").fetchall()}
    if "SCH_JUST_IND" in cols:
        return "2023-24"
    if "JJ" in cols:
        return "2021-22"
    raise SystemExit("Unrecognised CRDC layout: check this release field by field first.")


# 2023-24 publishes a high school's AP and IB "No" as -9. The School Form asks every school with
# grade 9-12 students both questions as required Yes/No items (APIB-1 and APIB-3), and the data
# dictionary lists both as Yes/No; nothing documents a recoding. Read as "No", the national rates
# match 2021-22 (AP 53.5% against 54.1%, IB 3.8% against 3.9%), so -9 at a regular high school is read
# as "No". It stays unknown at justice facilities, where a genuine skip is plausible, and for AP
# wherever the course count is not also -9 (63 schools report courses under a -9 indicator).
# Disclosed on Methodology. Only this release gets the rule; any other release without a "No" is
# refused by _check_indicator_vocabulary.
MINUS9_AS_NO = {
    "2023-24": {
        "SCH_APENR_IND": "c.SCH_JUST_IND = 'No' AND a.SCH_APCOURSES = '-9'",
        "SCH_IBENR_IND": "c.SCH_JUST_IND = 'No'",
    }
}


def _offer_ind_read(col: str, vintage: str) -> str:
    """_offer_ind, plus the documented -9 reading for the release it applies to."""
    short = col.split(".", 1)[1]
    cond = MINUS9_AS_NO.get(vintage, {}).get(short)
    if cond is None:
        return _offer_ind(col)
    return (
        f"CASE WHEN upper({col}) = 'YES' THEN TRUE WHEN upper({col}) = 'NO' THEN FALSE "
        f"WHEN {col} = '-9' AND {cond} THEN FALSE END"
    )


MIN_HS_FOR_VOCAB_CHECK = 100


def _check_indicator_vocabulary(con: duckdb.DuckDBPyConnection, vintage: str = "") -> None:
    """Refuse a release where a Yes/No offer indicator has no "No" among high schools.

    The 2023-24 CRDC publishes a high school's AP and IB "No" as -9 (Not Applicable/Skipped):
    10,102 high schools that answered "No" to AP in 2021-22 show -9 in 2023-24, and not one high
    school shows "No". Read naively, every high school without AP would become "not reported",
    and the offer rate would be computed over the schools that offer AP only. A "No"-less
    indicator is a coding change to resolve by hand, not data to publish.
    """
    n_hs = con.execute(f"SELECT count(*) FROM chars c WHERE {HS_WHERE}").fetchone()[0]
    if n_hs < MIN_HS_FOR_VOCAB_CHECK:
        return  # a hand-made fixture, not a release; a real release has about 27,000 high schools
    for view_name, col in (
        ("ap", "SCH_APENR_IND"),
        ("ib", "SCH_IBENR_IND"),
        ("dual", "SCH_DUAL_IND"),
    ):
        if col in MINUS9_AS_NO.get(vintage, {}):
            continue  # this release's "No" is -9, read by the documented rule above
        n_no = con.execute(
            f"SELECT count(*) FROM chars c JOIN {view_name} x USING (COMBOKEY) "
            f"WHERE ({HS_WHERE}) AND upper(x.{col}) = 'NO'"
        ).fetchone()[0]
        if n_no == 0:
            raise SystemExit(
                f"{col}: no high school reports 'No'. This release codes 'No' differently "
                "(2023-24 publishes it as -9). Resolve how to read -9 before building K-12."
            )


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

    present = frozenset(
        r[0]
        for v in ("enr", "ap", "calc", "phys", "cs", "chem", "dual", "ib", "gt")
        for r in con.execute(f"DESCRIBE {v}").fetchall()
    )
    vintage = _detect_vintage(con)
    _check_indicator_vocabulary(con, vintage)

    def _sum(alias: str, prefix: str) -> str:
        return _sum_races(alias, prefix, present=present)

    con.execute(
        f"""
        CREATE OR REPLACE TABLE k12 AS
        SELECT
            '{vintage}'                                  AS crdc_vintage,
            c.COMBOKEY                                   AS combokey,
            c.LEA_STATE                                  AS state,
            c.SCH_NAME                                   AS name,
            c.LEA_NAME                                   AS district,
            (upper(c.SCH_STATUS_CHARTER) = 'YES')        AS charter,
            (upper(c.SCH_STATUS_MAGNET) = 'YES')         AS magnet,
            {_sum("e", "SCH_ENR")}                          AS enroll_total,
            {_offer_ind_read("a.SCH_APENR_IND", vintage)}              AS offers_ap,
            {_posn("a.SCH_APCOURSES")}                   AS ap_courses,
            {_sum("a", "SCH_APENR")}                        AS ap_enroll,
            {_offer_cnt("m.SCH_MATHCLASSES_CALC")}       AS offers_calc,
            {_sum("m", "SCH_MATHENR_CALC")}                 AS calc_enroll,
            {_offer_cnt("p.SCH_SCICLASSES_PHYS")}        AS offers_physics,
            {_sum("p", "SCH_SCIENR_PHYS")}                  AS phys_enroll,
            {_offer_cnt("cs.SCH_COMPCLASSES_CSCI")}      AS offers_cs,
            {_sum("cs", "SCH_COMPENR_CSCI")}                AS cs_enroll,
            {_offer_cnt("ch.SCH_SCICLASSES_CHEM")}       AS offers_chem,
            {_sum("ch", "SCH_SCIENR_CHEM")}                 AS chem_enroll,
            {_offer_ind("d.SCH_DUAL_IND")}               AS offers_dual,
            {_sum("d", "SCH_DUALENR")}                      AS dual_enroll,
            {_offer_ind_read("ib.SCH_IBENR_IND", vintage)}             AS offers_ib,
            {_sum("ib", "SCH_IBENR")}                       AS ib_enroll,
            {_offer_ind("g.SCH_GT_IND")}                 AS offers_gt,
            {_sum("g", "SCH_GTENR")}                        AS gt_enroll,
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
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else (RAW_DIR / "crdc-2023-24")
    if not folder.exists():
        raise SystemExit(
            f"CRDC folder {folder} not found. Put the CRDC 'School' CSVs in {RAW_DIR / 'crdc-2023-24'} "
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
