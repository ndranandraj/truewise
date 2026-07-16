"""Build the Careers demand layer: what occupations a field of study leads to, with the
Bureau of Labor Statistics pay and 10-year outlook.

Three public inputs are joined (all downloaded by pipeline.download_bls, which runs where
there is network, NOT in the restricted build sandbox):

  1. NCES CIP-to-SOC crosswalk   -> which occupations (SOC codes) a field (CIP) leads to.
  2. BLS OEWS national wages     -> median annual wage per occupation.
  3. BLS Employment Projections  -> 10-year projected % change and annual openings per occupation.

The join is inherently many-to-many (a major maps to several occupations and vice-versa), so
the output is descriptive: for each 4-digit CIP we list the occupations it commonly leads to,
each with its BLS pay and outlook, plus a small summary (total annual openings across those
occupations and their median projected growth). The transform lives in `build_demand(con)`
so tests exercise exactly what ships.

Output: data/parquet/careers_demand.parquet with columns (cip_code, demand_json). build_careers
merges it into fields.json when present; wages ship with or without it.

Usage (from repo root, after download_bls has produced the three raw CSVs):
    python -m pipeline.build_careers_demand
"""

from __future__ import annotations

import duckdb

from pipeline.config import PARQUET_DIR, RAW_DIR

TOP_N = 6  # occupations listed per field, most annual openings first
OEWS_WAGE_CAP = 239200  # BLS reports '#' for annual wages at or above this cap


def build_demand(con: duckdb.DuckDBPyConnection, top_n: int = TOP_N) -> None:
    """Create a `careers_demand` table from `xwalk`, `oews`, `ep` tables on `con`.

    Expects each table to already expose normalized logical columns:
      xwalk(cip, soc)  oews(soc, title, wage)  ep(soc, growth, openings)
    with cip a 4-digit code (no dot) and soc a 6-digit code (e.g. '29-1141').
    """
    con.execute(
        f"""
        CREATE OR REPLACE TABLE careers_demand AS
        WITH occ AS (
            SELECT DISTINCT x.cip AS cip, x.soc AS soc, o.title AS title,
                   o.wage AS wage, e.growth AS growth, e.openings AS openings
            FROM xwalk x
            JOIN oews o USING (soc)
            LEFT JOIN ep e USING (soc)
            WHERE o.wage IS NOT NULL
        ),
        ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY cip ORDER BY openings DESC NULLS LAST, wage DESC
            ) AS rn
            FROM occ
        ),
        agg AS (
            SELECT cip,
                   round(median(growth)) AS growth_pct,
                   round(sum(openings))  AS annual_openings,
                   count(*)              AS n_occ
            FROM occ GROUP BY cip
        )
        SELECT
            a.cip AS cip_code,
            to_json({{
                'growth_pct': a.growth_pct,
                'annual_openings': a.annual_openings,
                'summary': 'Occupations this field commonly leads to, with BLS median pay and the '
                    || '2023-2033 outlook. Openings are the annual average across those occupations.',
                'occupations': (
                    SELECT list({{'soc': r.soc, 'title': r.title, 'wage': round(r.wage),
                                  'growth': r.growth, 'openings': round(r.openings)}}
                                 ORDER BY r.rn)
                    FROM ranked r WHERE r.cip = a.cip AND r.rn <= {top_n}
                )
            }}) AS demand_json
        FROM agg a
        """
    )


def _csv(name: str) -> str:
    hits = sorted(RAW_DIR.glob(f"*{name}*.csv"))
    if not hits:
        raise SystemExit(
            f"Missing {name}*.csv in {RAW_DIR}. Run `python -m pipeline.download_bls` "
            "first (on a machine with network access)."
        )
    return str(hits[-1])


def _load_raw(con: duckdb.DuckDBPyConnection) -> None:
    """Load the three canonical CSVs from download_bls and normalize into xwalk/oews/ep.

    download_bls has already reduced each messy source to simple columns:
      cip_soc_crosswalk.csv (cip, soc)  oews_national.csv (soc, title, wage)
      ep_projections.csv (soc, growth, openings)
    Here we only normalize the code formats and units: CIP to 4 digits (no dot), SOC to 6
    digits, the OEWS '#' wage cap to a number, and EP openings from thousands to a count.
    """
    con.execute(
        f"""CREATE OR REPLACE TABLE xwalk AS
        SELECT DISTINCT substr(replace(cip, '.', ''), 1, 4) AS cip, substr(soc, 1, 7) AS soc
        FROM read_csv('{_csv("cip_soc_crosswalk")}', all_varchar=true, header=true)
        WHERE cip IS NOT NULL AND soc IS NOT NULL"""
    )
    con.execute(
        f"""CREATE OR REPLACE TABLE oews AS
        SELECT substr(soc, 1, 7) AS soc, any_value(title) AS title,
               any_value(CASE WHEN trim(wage) = '#' THEN {OEWS_WAGE_CAP}
                              ELSE TRY_CAST(replace(replace(wage, ',', ''), '*', '') AS DOUBLE)
                         END) AS wage
        FROM read_csv('{_csv("oews_national")}', all_varchar=true, header=true)
        GROUP BY 1"""
    )
    con.execute(
        f"""CREATE OR REPLACE TABLE ep AS
        SELECT substr(soc, 1, 7) AS soc,
               any_value(TRY_CAST(growth AS DOUBLE)) AS growth,
               any_value(TRY_CAST(replace(openings, ',', '') AS DOUBLE) * 1000) AS openings
        FROM read_csv('{_csv("ep_projections")}', all_varchar=true, header=true)
        GROUP BY 1"""
    )


def main() -> None:
    con = duckdb.connect()
    _load_raw(con)
    build_demand(con)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    out = PARQUET_DIR / "careers_demand.parquet"
    con.execute(f"COPY careers_demand TO '{out}' (FORMAT PARQUET)")
    n = con.execute("SELECT count(*) FROM careers_demand").fetchone()[0]
    print(f"careers_demand: {n:,} fields with an occupation outlook")
    print(f"wrote -> {out}")


if __name__ == "__main__":
    main()
