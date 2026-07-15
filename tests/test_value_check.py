"""Unit tests for the Value Check earnings-premium logic and the column resolver.

These run without any download: we build a synthetic `fos` table in an in-memory
DuckDB and exercise the exact SQL that ships in value_check.build_value_check.
"""

from __future__ import annotations

import duckdb
import pytest

from pipeline.build_spine import resolve_columns
from pipeline.config import (
    FOS_FIELD_CANDIDATES,
    FOS_REQUIRED,
    INST_FIELD_CANDIDATES,
    INST_REQUIRED,
)
from pipeline.value_check import build_value_check

_NUMERIC = {
    "completers_count",
    "earnings_median_1yr",
    "earnings_median_4yr",
    "earn_gt_threshold_4yr",
    "earn_count_wne_4yr",
    "earn_gt_threshold_1yr",
    "earn_count_wne_1yr",
    "earnings_threshold_state",
    "earnings_threshold_national",
    "debt_median",
}

FOS_COLUMNS = [
    "unitid",
    "opeid6",
    "inst_name",
    "state",
    "control",
    "cip_code",
    "cip_desc",
    "credential_level",
    "credential_desc",
    "completers_count",
    "earnings_median_1yr",
    "earnings_median_4yr",
    "earn_gt_threshold_4yr",
    "earn_count_wne_4yr",
    "earn_gt_threshold_1yr",
    "earn_count_wne_1yr",
    "earnings_threshold_state",
    "earnings_threshold_national",
    "debt_median",
]


def _con_with_fos(rows: list[dict]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    cols_ddl = ", ".join(f"{c} DOUBLE" if c in _NUMERIC else f"{c} VARCHAR" for c in FOS_COLUMNS)
    con.execute(f"CREATE TABLE fos ({cols_ddl})")
    for r in rows:
        placeholders = ", ".join("?" for _ in FOS_COLUMNS)
        con.execute(
            f"INSERT INTO fos VALUES ({placeholders})",
            [r.get(c) for c in FOS_COLUMNS],
        )
    return con


def _row(**kw) -> dict:
    base = dict.fromkeys(FOS_COLUMNS)
    base.update(unitid="1", cip_code="5101", credential_level="3")
    base.update(kw)
    return base


def _flag(con, unitid: str) -> str:
    return con.execute("SELECT value_flag FROM value_check WHERE unitid = ?", [unitid]).fetchone()[
        0
    ]


def test_passes_when_earnings_above_state_threshold():
    con = _con_with_fos(
        [_row(unitid="pass", earnings_median_1yr=45000, earnings_threshold_state=30000)]
    )
    build_value_check(con)
    assert _flag(con, "pass") == "passes_earnings_premium"
    fails = con.execute("SELECT fails_ep_state FROM value_check WHERE unitid='pass'").fetchone()[0]
    assert fails is False


def test_fails_when_earnings_below_state_threshold():
    con = _con_with_fos(
        [_row(unitid="fail", earnings_median_1yr=22000, earnings_threshold_state=30000)]
    )
    build_value_check(con)
    assert _flag(con, "fail") == "fails_earnings_premium"
    assert (
        con.execute("SELECT fails_ep_state FROM value_check WHERE unitid='fail'").fetchone()[0]
        is True
    )


def test_insufficient_when_earnings_missing():
    con = _con_with_fos([_row(unitid="noe", earnings_threshold_state=30000)])
    build_value_check(con)
    assert _flag(con, "noe") == "insufficient_data"


def test_insufficient_when_threshold_missing():
    con = _con_with_fos([_row(unitid="not", earnings_median_1yr=40000)])
    build_value_check(con)
    assert _flag(con, "not") == "insufficient_data"


def test_earnings_horizon_prefers_4yr_then_falls_back_to_1yr():
    # Mirrors ED's published display: prefer 4-year earnings, fall back to 1-year.
    con = _con_with_fos(
        [
            _row(
                unitid="both",
                earnings_median_1yr=40000,
                earnings_median_4yr=60000,
                earnings_threshold_state=30000,
            ),
            _row(unitid="oneonly", earnings_median_1yr=40000, earnings_threshold_state=30000),
        ]
    )
    build_value_check(con)
    rows = dict(con.execute("SELECT unitid, earnings_horizon FROM value_check").fetchall())
    assert rows["both"] == "4yr_after_completion"
    assert rows["oneonly"] == "1yr_after_completion"
    # the earnings actually used for 'both' should be the 4-year value
    assert (
        con.execute("SELECT earnings FROM value_check WHERE unitid='both'").fetchone()[0] == 60000
    )


def test_debt_to_earnings_ratio_and_null_safety():
    con = _con_with_fos(
        [
            _row(
                unitid="ratio",
                earnings_median_1yr=40000,
                earnings_threshold_state=30000,
                debt_median=20000,
            ),
            _row(
                unitid="zero",
                earnings_median_1yr=0,
                earnings_threshold_state=30000,
                debt_median=20000,
            ),
        ]
    )
    build_value_check(con)
    ratio = con.execute(
        "SELECT debt_to_earnings_ratio FROM value_check WHERE unitid='ratio'"
    ).fetchone()[0]
    assert ratio == pytest.approx(0.5)
    # Division by zero earnings must not blow up -> NULL.
    assert (
        con.execute(
            "SELECT debt_to_earnings_ratio FROM value_check WHERE unitid='zero'"
        ).fetchone()[0]
        is None
    )


def test_share_earning_above_hs_grad():
    con = _con_with_fos(
        [
            _row(
                unitid="shr",
                earnings_median_1yr=40000,
                earnings_threshold_state=30000,
                earn_gt_threshold_1yr=30,
                earn_count_wne_1yr=40,
            ),
            _row(
                unitid="nodenom",
                earnings_median_1yr=40000,
                earnings_threshold_state=30000,
                earn_gt_threshold_1yr=30,
                earn_count_wne_1yr=0,
            ),
        ]
    )
    build_value_check(con)
    share = con.execute(
        "SELECT share_earning_above_hs_grad FROM value_check WHERE unitid='shr'"
    ).fetchone()[0]
    assert share == pytest.approx(0.75)
    # Zero denominator -> NULL, not an error.
    assert (
        con.execute(
            "SELECT share_earning_above_hs_grad FROM value_check WHERE unitid='nodenom'"
        ).fetchone()[0]
        is None
    )


def test_national_premium_independent_of_state():
    con = _con_with_fos(
        [
            _row(
                unitid="mix",
                earnings_median_1yr=32000,
                earnings_threshold_state=30000,
                earnings_threshold_national=35000,
            )
        ]
    )
    build_value_check(con)
    fs, fn = con.execute(
        "SELECT fails_ep_state, fails_ep_national FROM value_check WHERE unitid='mix'"
    ).fetchone()
    assert fs is False  # beats state threshold
    assert fn is True  # below national threshold


# --- column resolver -------------------------------------------------------


def test_resolve_fos_columns_picks_first_present_candidate():
    actual = ["UNITID", "CIPCODE", "CREDLEV", "EARN_MDN_1YR", "DEBT_ALL_STGP_EVAL_MDN"]
    resolved = resolve_columns(actual, FOS_FIELD_CANDIDATES, FOS_REQUIRED)
    assert resolved["unitid"] == "UNITID"
    assert resolved["earnings_median_1yr"] == "EARN_MDN_1YR"
    assert resolved["debt_median"] == "DEBT_ALL_STGP_EVAL_MDN"


def test_resolve_inst_columns_finds_thresholds():
    actual = ["UNITID", "STABBR", "EARN_THR_STATE", "EARN_THR_NAT"]
    resolved = resolve_columns(actual, INST_FIELD_CANDIDATES, INST_REQUIRED)
    assert resolved["earnings_threshold_state"] == "EARN_THR_STATE"
    assert resolved["earnings_threshold_national"] == "EARN_THR_NAT"


def test_resolve_columns_raises_when_required_missing():
    with pytest.raises(SystemExit):
        resolve_columns(["UNITID", "CIPCODE"], FOS_FIELD_CANDIDATES, FOS_REQUIRED)
