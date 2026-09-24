"""One program, counted once: the unit behind every aggregate figure on the site.

The College Scorecard Field-of-Study file has one row per campus (UNITID) x field (4-digit CIP) x
credential. But ED computes earnings and debt at the federal-aid level (six-digit OPEID) and
repeats the same figures on every campus that shares the OPEID: Penn State's campuses, chain
cosmetology schools, multi-campus systems. Counting each campus row as a program counted those
programs several times (7,694 duplicate judged rows in the June 2026 release).

So every aggregate (the headline, the chart, lists, majors, careers, findings) counts a program
once per OPEID6 x CIP x credential. Earnings and debt are identical across the group, so any row
carries them; completers are per campus, so they are summed.

The verdict is the one thing that can differ across a group, because campuses in different states
are compared with different state lines (48 groups). The federal rule compares an institution
with the line of the state where it is located, so the group takes the verdict of ED's main campus
(MAIN = 1 in the Institution file); every such group in the current release contains its main
campus. Groups without a decided main-campus row take any decided row, lowest UNITID first, so
the choice is deterministic.

College profiles are not affected: each campus page still shows its own rows, and says when the
figures are shared with other campuses.

Main-campus flags come from ED's Institution file, which is not part of the deploy, so they are
committed as published/main_campus.parquet (built by `python -m pipeline.program_unit`).
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from pipeline.config import RAW_DIR, ROOT

PUBLISHED = ROOT / "published"
MAIN_CAMPUS = PUBLISHED / "main_campus.parquet"
INSTITUTION_CSV = RAW_DIR / "Most-Recent-Cohorts-Institution.csv"

# Scorecard CREDLEV: 1 undergraduate certificate, 2 associate, 3 bachelor's. The federal
# earnings-premium test for these compares graduates with high-school graduates; graduate
# credentials (4 to 8) are judged against a bachelor's-holder line under the 2026 rule, and 99 is
# not a credential. The headline is therefore undergraduate-only.
UNDERGRAD_LEVELS = ("1", "2", "3")


def programs_sql(vc_path: Path | str, main_path: Path | str = MAIN_CAMPUS) -> str:
    """A SELECT with value_check's columns plus n_campuses, one row per OPEID6 x CIP x credential."""
    vc = str(vc_path).replace("'", "''")
    main = str(main_path).replace("'", "''")
    cols = {
        r[0]
        for r in duckdb.connect().execute(f"DESCRIBE SELECT * FROM read_parquet('{vc}')").fetchall()
    }
    if not {"cip_code", "credential_level"} <= cols:
        # A hand-made fixture with no field or credential: every row is already one program.
        return f"(SELECT *, 1 AS n_campuses FROM read_parquet('{vc}'))"
    # A table without OPEID6 (a hand-made fixture) has nothing to share across campuses: each
    # campus row is its own program. Missing columns are supplied as NULL so the shape is the same.
    unit = "'unit:' || CAST(v.unitid AS VARCHAR)"
    grp = f"coalesce(v.opeid6, {unit})" if "opeid6" in cols else unit
    extra = "" if "completers_count" in cols else ", NULL::DOUBLE AS completers_count"
    main_join = (
        f"LEFT JOIN read_parquet('{main}') m ON m.unitid = CAST(v.unitid AS VARCHAR)"
        if Path(main_path).exists()
        else ""
    )
    main_flag = "(m.unitid IS NOT NULL)" if main_join else "FALSE"
    decided = "(v.value_flag != 'insufficient_data')" if "value_flag" in cols else "TRUE"
    return f"""
    (WITH rows AS (
        SELECT v.*{extra},
               {grp} AS _grp,
               {main_flag} AS _main,
               {decided} AS _decided
        FROM read_parquet('{vc}') v
        {main_join}
    ),
    ranked AS (
        SELECT *,
               row_number() OVER (
                   PARTITION BY _grp, cip_code, credential_level
                   ORDER BY _decided DESC, _main DESC, unitid
               ) AS _rk,
               count(*) OVER (PARTITION BY _grp, cip_code, credential_level) AS n_campuses,
               sum(completers_count) OVER (PARTITION BY _grp, cip_code, credential_level)
                   AS _completers_sum
        FROM rows
    )
    SELECT * EXCLUDE (_grp, _main, _decided, _rk, completers_count, _completers_sum),
           _completers_sum AS completers_count
    FROM ranked WHERE _rk = 1)
    """


def undergrad(alias: str = "") -> str:
    """SQL predicate for the headline population."""
    col = f"{alias}.credential_level" if alias else "credential_level"
    return f"{col} IN ({', '.join(repr(x) for x in UNDERGRAD_LEVELS)})"


def main() -> None:
    """Write published/main_campus.parquet from ED's Institution file (run where raw data lives)."""
    if not INSTITUTION_CSV.exists():
        raise SystemExit(f"{INSTITUTION_CSV} not found; download the Scorecard files first.")
    con = duckdb.connect()
    src = str(INSTITUTION_CSV).replace("'", "''")
    con.execute(
        f"COPY (SELECT DISTINCT UNITID AS unitid FROM read_csv('{src}', all_varchar=true, "
        f"header=true) WHERE MAIN = '1' ORDER BY unitid) TO '{MAIN_CAMPUS}' (FORMAT PARQUET)"
    )
    n = con.execute(f"SELECT count(*) FROM read_parquet('{MAIN_CAMPUS}')").fetchone()[0]
    print(f"main campuses: {n:,}\nwrote -> {MAIN_CAMPUS}")


if __name__ == "__main__":
    main()
