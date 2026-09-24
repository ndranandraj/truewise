"""Counting a program once, and saying honestly what each profile row is.

The September 2026 audit found the headline counted campus rows, so a program ED reports for 19
Penn State campuses counted 19 times, and that graduate programs were judged against a high-school
line and called the federal test. These pin the fix.
"""

from __future__ import annotations

import duckdb

from pipeline.build_profile_pilot import _row_from, payback_text, verdict_chip
from pipeline.program_unit import programs_sql, undergrad


def _fixture(tmp_path):
    con = duckdb.connect()
    rows = [
        # unitid, opeid6, state, cip, level, earnings, flag, completers
        ("1", "000001", "PA", "5201", "3", 30000.0, "passes_earnings_premium", 10),
        ("2", "000001", "OH", "5201", "3", 30000.0, "fails_earnings_premium", 20),
        ("3", "000001", "PA", "5201", "3", 30000.0, "passes_earnings_premium", 5),
        ("4", "000002", "TX", "1204", "1", 20000.0, "fails_earnings_premium", 7),
        ("5", "000002", "TX", "1204", "5", 90000.0, "passes_earnings_premium", 3),
    ]
    con.execute(
        "CREATE TABLE v (unitid VARCHAR, opeid6 VARCHAR, state VARCHAR, cip_code VARCHAR, "
        "credential_level VARCHAR, earnings DOUBLE, value_flag VARCHAR, completers_count DOUBLE)"
    )
    con.executemany("INSERT INTO v VALUES (?,?,?,?,?,?,?,?)", rows)
    vc = tmp_path / "vc.parquet"
    con.execute(f"COPY v TO '{vc}' (FORMAT PARQUET)")
    main = tmp_path / "main.parquet"
    con.execute(f"COPY (SELECT '2' AS unitid) TO '{main}' (FORMAT PARQUET)")
    return con, vc, main


def test_a_program_shared_by_campuses_counts_once_with_the_main_campus_verdict(tmp_path):
    con, vc, main = _fixture(tmp_path)
    got = con.execute(
        f"SELECT opeid6, value_flag, completers_count, n_campuses FROM {programs_sql(vc, main)} "
        "WHERE cip_code = '5201'"
    ).fetchall()
    # Three campus rows, one program. The main campus (unitid 2, in Ohio) decides the verdict,
    # as the federal rule compares an institution with the state where it is located.
    assert got == [("000001", "fails_earnings_premium", 35.0, 3)]


def test_the_headline_population_is_undergraduate(tmp_path):
    con, vc, main = _fixture(tmp_path)
    n = con.execute(f"SELECT count(*) FROM {programs_sql(vc, main)} WHERE {undergrad()}").fetchone()
    assert n[0] == 2, "the master's row is not in the undergraduate headline"


def _row(**kw):
    base = {
        "cip_code": "5201",
        "cip_desc": "Business Administration.",
        "credential_desc": "Bachelor's Degree",
        "credential_level": "3",
        "earnings": 50000.0,
        "earnings_premium_state": 15000.0,
        "earnings_threshold_state": 35000.0,
        "debt_median": 20000.0,
        "debt_payback_years": 1.3,
        "completers_count": 40,
        "value_flag": "passes_earnings_premium",
        "earnings_horizon": "4yr_after_completion",
    }
    base.update(kw)
    return _row_from(base)


def test_published_earnings_without_a_benchmark_are_shown_not_hidden():
    r = _row(value_flag="insufficient_data", earnings_threshold_state=None)
    assert r["verdict"] == "nobench" and r["earnings"] == 50000
    assert "no state benchmark" in verdict_chip(r)


def test_graduate_rows_are_not_called_the_federal_bar():
    r = _row(credential_level="5", credential_desc="Master's Degree")
    chip = verdict_chip(r)
    assert "above HS line" in chip and "clears the bar" not in chip
    assert "falls short" in verdict_chip(_row(value_flag="fails_earnings_premium"))


def test_no_earnings_gain_is_said_not_shown_as_missing():
    r = _row(
        value_flag="fails_earnings_premium", earnings_premium_state=-2000.0, debt_payback_years=None
    )
    assert "no earnings gain" in payback_text(r)
    assert payback_text(_row()) == "1.3 yrs"


def test_the_js_table_mirrors_the_static_labels():
    from pipeline.config import ROOT

    js = (ROOT / "site" / "components" / "table.js").read_text()
    for text in ("no state benchmark", "HS line", "no earnings gain", "Debt as years of gain"):
        assert text in js, f"table.js must render {text!r} like the static row"
    assert "Years to repay" not in js
