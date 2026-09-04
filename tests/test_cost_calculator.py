"""Test the "what would this cost you" calculator baked into each college page.

The calculator multiplies published net-price figures by a user-chosen number of years, so the
risks are (a) inventing a number where the data is suppressed and (b) implying a forecast. These
tests pin both: suppressed income bands must be disabled and labelled, and the honesty caveats
must be present on every page that shows the calculator.
"""

from __future__ import annotations

import json
import re

import duckdb

import pipeline.build_college_pages as bcp
import pipeline.build_site as bs
from tests.test_college_pages import INST_COLS, VC_COLS


def _build(tmp_path, monkeypatch, register_fixture_slugs, net_price_row):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({VC_COLS})")
    thr = 35000.0
    con.executemany(
        f"INSERT INTO vc VALUES ({','.join(['?'] * 17)})",
        [
            (
                "100",
                "Test University",
                "TX",
                "Public",
                "5201",
                "Business.",
                "3",
                "Bachelor's Degree",
                100,
                70000.0,
                "4yr_after_completion",
                thr,
                35000.0,
                20000.0,
                0.29,
                2.0,
                "passes_earnings_premium",
            ),
            (
                "100",
                "Test University",
                "TX",
                "Public",
                "1104",
                "Computer Science.",
                "3",
                "Bachelor's Degree",
                80,
                90000.0,
                "4yr_after_completion",
                thr,
                55000.0,
                20000.0,
                0.22,
                4.0,
                "passes_earnings_premium",
            ),
        ],
    )
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")
    con.execute(f"CREATE TABLE inst({INST_COLS})")
    con.execute(f"INSERT INTO inst VALUES {net_price_row}")
    con.execute(f"COPY inst TO '{pq / 'institutions.parquet'}' (FORMAT PARQUET)")

    monkeypatch.setattr(bs, "PARQUET_DIR", pq)
    monkeypatch.setattr(bcp, "SITE", tmp_path / "site")
    # Builders resolve slugs strictly from the registry, so register these synthetic schools first.
    register_fixture_slugs()
    bcp.main()
    return (tmp_path / "site" / "college" / "test-university" / "index.html").read_text()


def test_calculator_uses_real_figures_and_states_assumptions(
    tmp_path, monkeypatch, register_fixture_slugs
):
    html = _build(
        tmp_path,
        monkeypatch,
        register_fixture_slugs,
        "('100','Austin','http://x',5000,18000,12000,14000,20000,24000,28000,0.4,0.3,0.75)",
    )
    data = json.loads(re.search(r'id="calc-data">(.*?)</script>', html).group(1))
    # Inputs are the published figures, not derived guesses.
    assert data["brackets"] == [12000, 14000, 20000, 24000, 28000]
    assert data["avg"] == 18000
    # Median payback across this school's passing programs (2.0 and 4.0 -> 3.0).
    assert data["payback"] == 3.0
    # The honesty guardrails must ship with every calculator.
    assert "not a quote or a prediction" in html
    assert "does not include interest" in html
    assert "assumes aid and price stay flat" in html


def test_suppressed_income_band_is_disabled_never_guessed(
    tmp_path, monkeypatch, register_fixture_slugs
):
    # Middle bracket ($48k-$75k) is NULL, i.e. privacy-suppressed.
    html = _build(
        tmp_path,
        monkeypatch,
        register_fixture_slugs,
        "('100','Austin','http://x',5000,18000,12000,14000,NULL,24000,28000,0.4,0.3,0.75)",
    )
    data = json.loads(re.search(r'id="calc-data">(.*?)</script>', html).group(1))
    assert data["brackets"][2] is None, "suppressed bracket must stay null, never imputed"
    options = re.search(r'id="calc-income">(.*?)</select>', html).group(1)
    assert options.count("disabled") == 1
    assert "(not reported)" in options
