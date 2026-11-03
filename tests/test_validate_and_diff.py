"""Unit tests for the data-quality checks (analysis.validate) and the Monitor diff engine."""

from __future__ import annotations

import duckdb

from analysis.validate import CHECKS
from pipeline.config import ARCHIVE_DIR
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


def _vc_payback(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE TABLE vc (value_flag VARCHAR, debt_payback_years DOUBLE)")
    con.executemany("INSERT INTO vc VALUES (?,?)", rows)
    return con


def test_debt_payback_sane_flags_bad_rows():
    # Valid: positive payback on a passing program; null elsewhere.
    ok, _ = CHECKS["debt_payback_sane"](
        _vc_payback([("passes_earnings_premium", 1.3), ("fails_earnings_premium", None)])
    )
    assert ok
    # A payback set on a failing program is a bug.
    bad_flag, _ = CHECKS["debt_payback_sane"](_vc_payback([("fails_earnings_premium", 2.0)]))
    assert not bad_flag
    # A non-positive payback is a bug.
    bad_val, _ = CHECKS["debt_payback_sane"](_vc_payback([("passes_earnings_premium", -1.0)]))
    assert not bad_val


# --- diff engine -----------------------------------------------------------

_SNAP_COLS = (
    "unitid VARCHAR, opeid6 VARCHAR, cip_code VARCHAR, credential_level VARCHAR, "
    "credential_desc VARCHAR, inst_name VARCHAR, value_flag VARCHAR, earnings DOUBLE"
)


def _snap(con, name, rows):
    con.execute(f"CREATE TABLE {name} ({_SNAP_COLS})")
    con.executemany(
        f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?,?)",
        [(r[0], "000001", *r[1:]) for r in rows],
    )


def _schools(con, name, rows):
    """Rows of (unitid, opeid6, name, flag, earnings) at one CIP and credential."""
    con.execute(f"CREATE TABLE {name} ({_SNAP_COLS})")
    con.executemany(
        f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?,?)",
        [(u, o, "0101", "3", "BA", inst, flag, earn) for u, o, inst, flag, earn in rows],
    )


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


def test_rows_with_no_unitid_pair_only_with_the_same_school():
    """Pairing every UNITID "NA" row at a CIP and credential invented 21,404 revisions on real data."""
    flag = "insufficient_data"
    same = [
        ("NA", "000010", "Closed A", flag, 40000.0),
        ("NA", "000020", "Closed B", flag, 90000.0),
    ]
    con = duckdb.connect()
    _schools(
        con,
        "old",
        [
            *same,
            ("NA", "000030", "Closed C", flag, 50000.0),
            ("NA", "000040", "Closed D", flag, 6e4),
        ],
    )
    _schools(
        con,
        "new",
        [
            *same,
            ("NA", "000030", "Closed C", flag, 52000.0),
            ("NA", "000050", "Closed E", flag, 7e4),
        ],
    )
    d = compute_diff(con)
    assert [(r["inst_name"], r["old_earn"], r["new_earn"]) for r in d["earnings_revised"]] == [
        ("Closed C", 50000.0, 52000.0)
    ]
    assert [r["inst_name"] for r in d["removed"]] == ["Closed D"]
    assert [r["inst_name"] for r in d["added"]] == ["Closed E"]


def test_a_school_whose_opeid6_changes_keeps_its_programs():
    """A real UNITID is enough: a new OPEID6 must not read as every program removed and added."""
    con = duckdb.connect()
    _schools(con, "old", [("100", "000100", "A Univ", "passes_earnings_premium", 50000.0)])
    _schools(con, "new", [("100", "000999", "A Univ", "fails_earnings_premium", 30000.0)])
    d = compute_diff(con)
    assert not d["added"] and not d["removed"]
    assert [r["inst_name"] for r in d["newly_failing"]] == ["A Univ"]
    assert [r["inst_name"] for r in d["earnings_revised"]] == ["A Univ"]


def test_archived_snapshots_diffed_against_themselves_list_nothing():
    """Real rows, so this also fails on a release where a program's key stops being unique."""
    snapshots = sorted(ARCHIVE_DIR.glob("*/value_check_snapshot.parquet"))
    assert snapshots
    for path in snapshots:
        con = duckdb.connect()
        for name in ("old", "new"):
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{path}')")
        d = compute_diff(con)
        assert {k: len(v) for k, v in d.items()} == dict.fromkeys(d, 0), path
