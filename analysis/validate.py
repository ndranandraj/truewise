"""Data-quality gate for the Value Check dataset.

Runs a battery of checks against the built `value_check` table so a bad data refresh
(schema drift, a broken join, an imputation bug, another wrong-earnings-horizon slip)
fails loudly instead of shipping. Used two ways:

  * `python -m analysis.validate`, checks data/parquet/value_check.parquet; exit 1 on failure.
  * the FVT Monitor workflow runs it before committing a refresh.

Each check is a small function taking a DuckDB connection that has a `vc` view and
returning (passed: bool, detail: str). Checks are unit-tested on synthetic data.
"""

from __future__ import annotations

from collections.abc import Callable

import duckdb

Check = Callable[[duckdb.DuckDBPyConnection], "tuple[bool, str]"]
CHECKS: dict[str, Check] = {}


def check(name: str):
    def deco(fn: Check) -> Check:
        CHECKS[name] = fn
        return fn

    return deco


def _scalar(con, sql: str):
    return con.execute(sql).fetchone()[0]


@check("row_count_in_range")
def _row_count(con):
    n = _scalar(con, "SELECT count(*) FROM vc")
    return 150_000 <= n <= 400_000, f"{n:,} rows"


@check("flags_are_valid")
def _flags(con):
    bad = _scalar(
        con,
        "SELECT count(*) FROM vc WHERE value_flag NOT IN "
        "('passes_earnings_premium','fails_earnings_premium','insufficient_data')",
    )
    return bad == 0, f"{bad} rows with an unexpected value_flag"


@check("no_imputation_of_suppressed")
def _no_imputation(con):
    # An insufficient_data row must be missing earnings or the state threshold ,
    # i.e. we never labelled a fully-populated row insufficient, nor vice-versa.
    bad = _scalar(
        con,
        "SELECT count(*) FROM vc WHERE value_flag='insufficient_data' "
        "AND earnings IS NOT NULL AND earnings_threshold_state IS NOT NULL",
    )
    decided_missing = _scalar(
        con,
        "SELECT count(*) FROM vc WHERE value_flag!='insufficient_data' "
        "AND (earnings IS NULL OR earnings_threshold_state IS NULL)",
    )
    ok = bad == 0 and decided_missing == 0
    return ok, f"{bad} insufficient-but-complete, {decided_missing} decided-but-missing"


@check("threshold_values_sane")
def _threshold(con):
    lo, hi = con.execute(
        "SELECT min(earnings_threshold_state), max(earnings_threshold_state) "
        "FROM vc WHERE earnings_threshold_state IS NOT NULL"
    ).fetchone()
    ok = lo is not None and 10_000 <= lo and hi <= 80_000
    return ok, f"state threshold range {lo}-{hi} (expected ~10k-80k)"


@check("threshold_join_coverage")
def _join(con):
    frac = _scalar(
        con,
        "SELECT count(*) FILTER (WHERE earnings_threshold_state IS NOT NULL)*1.0/count(*) FROM vc",
    )
    return frac >= 0.85, f"{100 * frac:.1f}% of programs have a state threshold"


@check("decided_fraction_reasonable")
def _decided(con):
    frac = _scalar(
        con,
        "SELECT count(*) FILTER (WHERE value_flag!='insufficient_data')*1.0/count(*) FROM vc",
    )
    return 0.10 <= frac <= 0.60, f"{100 * frac:.1f}% decided"


@check("fail_rate_reasonable")
def _fail_rate(con):
    frac = _scalar(
        con,
        "SELECT count(*) FILTER (WHERE value_flag='fails_earnings_premium')*1.0/"
        "nullif(count(*) FILTER (WHERE value_flag!='insufficient_data'),0) FROM vc",
    )
    return frac is not None and 0.01 <= frac <= 0.40, f"{100 * frac:.1f}% of decided fail"


@check("earnings_positive")
def _earnings_pos(con):
    bad = _scalar(con, "SELECT count(*) FROM vc WHERE earnings IS NOT NULL AND earnings <= 0")
    return bad == 0, f"{bad} rows with non-positive earnings"


@check("debt_payback_sane")
def _payback(con):
    # Debt payback must be positive and finite where present, and only ever set on a
    # passing program (a fail or insufficient row has no premium to recoup the debt).
    bad = _scalar(
        con,
        "SELECT count(*) FROM vc WHERE debt_payback_years IS NOT NULL "
        "AND (debt_payback_years <= 0 OR value_flag != 'passes_earnings_premium')",
    )
    return bad == 0, f"{bad} rows with an invalid debt_payback_years"


@check("flag_matches_premium")
def _consistency(con):
    bad = _scalar(
        con,
        "SELECT count(*) FROM vc WHERE fails_ep_state IS NOT NULL "
        "AND fails_ep_state != (earnings < earnings_threshold_state)",
    )
    return bad == 0, f"{bad} rows where fails_ep_state disagrees with earnings<threshold"


def run(con: duckdb.DuckDBPyConnection) -> list[tuple[str, bool, str]]:
    """Run every check against a connection that already has a `vc` view."""
    return [(name, *fn(con)) for name, fn in CHECKS.items()]


def check_net_price(inst_path) -> tuple[bool, str]:
    """Affordability sanity: net price values within a plausible range."""
    con = duckdb.connect()
    cols = [
        "net_price_avg",
        *[f"net_price_{b}" for b in ("0_30k", "30_48k", "48_75k", "75_110k", "110k_plus")],
    ]
    con.execute(f"CREATE VIEW inst AS SELECT * FROM read_parquet('{inst_path}')")
    # Net price can be modestly negative (aid exceeds cost at low-cost schools); bounds
    # are set to allow legitimate values and catch true garbage.
    conds = " OR ".join(f"({c} IS NOT NULL AND ({c} < -15000 OR {c} > 150000))" for c in cols)
    bad = con.execute(f"SELECT count(*) FROM inst WHERE {conds}").fetchone()[0]
    return bad == 0, f"{bad} schools with implausible net price"


def main() -> None:
    from pipeline.config import PARQUET_DIR

    path = PARQUET_DIR / "value_check.parquet"
    if not path.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW vc AS SELECT * FROM read_parquet('{path}')")
    results = run(con)
    inst_path = PARQUET_DIR / "institutions.parquet"
    if inst_path.exists():
        results.append(("net_price_within_bounds", *check_net_price(inst_path)))
    failed = 0
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:32s} {detail}")
        failed += not ok
    if failed:
        raise SystemExit(f"\nData-quality gate FAILED: {failed} of {len(results)} checks.")
    print(f"\nData-quality gate passed: {len(results)}/{len(results)} checks.")


if __name__ == "__main__":
    main()
