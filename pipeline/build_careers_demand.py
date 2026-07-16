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

from pipeline.build_spine import resolve_columns
from pipeline.config import PARQUET_DIR, RAW_DIR

TOP_N = 6  # occupations listed per field, most annual openings first

# Candidate column names in each raw file (first present wins), resilient to release renames.
XWALK_CANDIDATES = {
    "cip": ["CIP2020Code", "CIPCode", "CIP2020", "CIPCODE"],
    "soc": ["SOC2018Code", "SOCCode", "SOC2018", "SOCCODE"],
}
OEWS_CANDIDATES = {
    "soc": ["OCC_CODE", "SOC", "occ_code"],
    "title": ["OCC_TITLE", "occ_title"],
    "wage": ["A_MEDIAN", "a_median", "MEDIAN_WAGE"],
}
EP_CANDIDATES = {
    "soc": ["Occupation Code", "SOC Code", "occ_code", "OCC_CODE"],
    "growth": [
        "Employment Percent Change, 2023-2033",
        "Employment Percent Change",
        "pct_change",
    ],
    "openings": [
        "Occupational Openings, 2023-2033 Annual Average",
        "Annual Average Openings",
        "annual_openings",
    ],
}


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


def _load_raw(con: duckdb.DuckDBPyConnection) -> None:
    """Load the three raw CSVs and normalize them into xwalk/oews/ep tables."""
    files = {
        "xwalk_raw": ("cip_soc_crosswalk", XWALK_CANDIDATES, ["cip", "soc"]),
        "oews_raw": ("oews_national", OEWS_CANDIDATES, ["soc", "wage"]),
        "ep_raw": ("ep_projections", EP_CANDIDATES, ["soc"]),
    }
    resolved = {}
    for tbl, (needle, cands, required) in files.items():
        hits = sorted(RAW_DIR.glob(f"*{needle}*.csv"))
        if not hits:
            raise SystemExit(
                f"Missing {needle}*.csv in {RAW_DIR}. Run `python -m pipeline.download_bls` "
                "first (on a machine with network access)."
            )
        con.execute(
            f"CREATE OR REPLACE TABLE {tbl} AS "
            "SELECT * FROM read_csv(?, all_varchar=true, header=true, sample_size=-1)",
            [str(hits[-1])],
        )
        cols = [r[0] for r in con.execute(f"DESCRIBE {tbl}").fetchall()]
        resolved[tbl] = resolve_columns(cols, cands, required)

    x = resolved["xwalk_raw"]
    con.execute(
        f"""CREATE OR REPLACE TABLE xwalk AS
        SELECT DISTINCT substr(replace("{x["cip"]}", '.', ''), 1, 4) AS cip,
                        substr("{x["soc"]}", 1, 7) AS soc
        FROM xwalk_raw
        WHERE "{x["cip"]}" IS NOT NULL AND "{x["soc"]}" IS NOT NULL"""
    )
    o = resolved["oews_raw"]
    con.execute(
        f"""CREATE OR REPLACE TABLE oews AS
        SELECT substr("{o["soc"]}", 1, 7) AS soc, any_value("{o["title"]}") AS title,
               TRY_CAST(replace(replace("{o["wage"]}", ',', ''), '*', '') AS DOUBLE) AS wage
        FROM oews_raw GROUP BY 1"""
    )
    e = resolved["ep_raw"]
    con.execute(
        f"""CREATE OR REPLACE TABLE ep AS
        SELECT substr("{e["soc"]}", 1, 7) AS soc,
               TRY_CAST("{e["growth"]}" AS DOUBLE) AS growth,
               TRY_CAST(replace("{e["openings"]}", ',', '') AS DOUBLE) AS openings
        FROM ep_raw"""
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
