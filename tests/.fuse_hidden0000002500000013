"""Unit tests for the data-quality checks (analysis.validate) and the Monitor diff engine."""

from __future__ import annotations

import duckdb

from analysis.validate import CHECKS
from pipeline.monitor_diff import compute_diff

# --- validation checks -----------------------------------------------------

_VC_COLS = (
    "value_flag VARCHAR, earnings DOUBLE, earnings_threshold_state DOUBLE, fails_ep_state BOOLEAN"
)


def _vc(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc ({_VC_COLS})")
    con.executemany("INSERT INTO vc VALUES (?,?,?,?)", rows)
    return con


def test_flags_are_valid_detects_bad_flag():
    ok, _ = CHECKS["flags_are_valid"](_vc([("passes_earnings_premium", 50000, 35000, False)]))
    assert ok
    bad, _ = CHECKS["flags_are_valid"](_vc([("mystery_flag", 50000, 35000, False)]))
    assert not bad


def test_no_imputation_detects_complete_insufficient_row():
    # An insufficient row that actually has both earnings and threshold is a bug.
    ok, _ = CHECKS["no_imputation_of_suppressed"](_vc([("insufficient_data", 50000, 35000, None)]))
    assert not ok
    clean, _ = CHECKS["no_imputation_of_suppressed"](
        _vc(
            [("insufficient_data", None, 35000, None), ("passes_earnings_premium", 5e4, 3e4, False)]
        )
    )
    assert clean


def test_flag_matches_premium_detects_inconsistency():
    # fails_ep_state says False but earnings are below threshold -> inconsistent.
    ok, _ = CHECKS["flag_matches_premium"](_vc([("passes_earnings_premium", 20000, 35000, False)]))
    assert not ok
    good, _ = CHECKS["flag_matches_premium"](_vc([("fails_earnings_premium", 20000, 35000, True)]))
    assert good


def test_earnings_positive_detects_nonpositive():
    ok, _ = CHECKS["earnings_positive"](_vc([("passes_earnings_premium", -5, 35000, None)]))
    assert not ok


# --- diff engine -----------------------------------------------------------

_SNAP_COLS = (
    "unitid VARCHAR, cip_code VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, "
    "inst_name VARCHAR, value_flag VARCHAR, earnings DOUBLE"
)


def _snap(con, name, rows):
    con.execute(f"CREATE TABLE {name} ({_SNAP_COLS})")
    con.executemany(f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?)", rows)


def test_compute_diff_categories():
    con = duckdb.connect()
    # key = unitid+cip+credlev
    _snap(
        con,
        "old",
        [
            ("1", "01", "3", "BA", "A Univ", "passes_earnings_premium", 50000),  # -> will fail
            ("1", "02", "3", "BA", "A Univ", "fails_earnings_premium", 20000),  # -> will pass
            (
                "1",
                "03",
                "3",
                "BA",
                "A Univ",
                "passes_earnings_premium",
                60000,
            ),  # -> earnings revised
            ("1", "04", "3", "BA", "A Univ", "passes_earnings_premium", 40000),  # -> removed
        ],
    )
    _snap(
        con,
        "new",
        [
            ("1", "01", "3", "BA", "A Univ", "fails_earnings_premium", 30000),
            ("1", "02", "3", "BA", "A Univ", "passes_earnings_premium", 45000),
            ("1", "03", "3", "BA", "A Univ", "passes_earnings_premium", 68000),  # +8000
            ("1", "05", "3", "BA", "A Univ", "passes_earnings_premium", 55000),  # added
        ],
    )
    d = compute_diff(con)
    assert [r["cip"] for r in d["newly_failing"]] == ["01"]
    assert [r["cip"] for r in d["newly_passing"]] == ["02"]
    assert [r["cip"] for r in d["added"]] == ["05"]
    assert [r["cip"] for r in d["removed"]] == ["04"]
    revised_cips = {r["cip"] for r in d["earnings_revised"]}
    assert "03" in revised_cips  # 60k -> 68k crosses the $1000 threshold
