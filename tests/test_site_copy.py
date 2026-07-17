"""Guardrail: published site copy must match the committed data.

The homepage and methodology page hard-code a handful of headline figures (1 in 11, 96%
of cosmetology, the 26% denominator, the total, and the Baylor example). Hand-typed numbers
drift from the data (this exact class of bug was found twice in review). This test recomputes
each figure from the committed parquet (published/value_check.parquet) and asserts the exact
string appears in the HTML, so copy can never silently disagree with the data again.
"""

from __future__ import annotations

import duckdb

from pipeline.config import ROOT

PARQUET = ROOT / "published" / "value_check.parquet"
HOME = ROOT / "site" / "index.html"
METH = ROOT / "site" / "methodology" / "index.html"


def _con():
    con = duckdb.connect()
    con.execute(f"CREATE VIEW v AS SELECT * FROM read_parquet('{PARQUET}')")
    return con


def test_headline_figures_match_data():
    con = _con()
    total, decided, fails = con.execute(
        "SELECT count(*), "
        "count(*) FILTER (WHERE value_flag != 'insufficient_data'), "
        "count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') FROM v"
    ).fetchone()
    one_in = round(decided / fails)  # 1 in 11
    share = round(100 * decided / total)  # 26
    cosmo = round(
        con.execute(
            "SELECT 100.0 * count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') "
            "/ count(*) FILTER (WHERE value_flag != 'insufficient_data') FROM v WHERE cip_code = '1204'"
        ).fetchone()[0]
    )  # 96
    d4, f4 = con.execute(
        "SELECT count(*) FILTER (WHERE value_flag != 'insufficient_data'), "
        "count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') "
        "FROM v WHERE earnings_horizon = '4yr_after_completion'"
    ).fetchone()
    strict = round(d4 / f4)  # 1 in 14

    home = HOME.read_text()
    meth = METH.read_text()

    # Headline finding, on both pages.
    assert f"1 in {one_in}" in home, f"homepage missing '1 in {one_in}'"
    assert f"1 in {one_in}" in meth
    # Cosmetology fail rate.
    assert f"{cosmo}%" in home and f"{cosmo}%" in meth
    # Methodology-only figures.
    assert f"{total:,}" in meth, f"methodology missing total {total:,}"
    assert f"about {share}%" in meth, f"methodology missing 'about {share}%'"
    assert f"1 in {strict}" in meth, f"methodology missing strict-4yr '1 in {strict}'"


def test_baylor_example_card_matches_data():
    bay = (
        _con()
        .execute(
            "SELECT earnings, earnings_premium_state, earnings_threshold_state FROM v "
            "WHERE inst_name ILIKE '%Baylor Univ%' AND cip_desc ILIKE 'Psychology, General%' "
            "AND credential_level = '3'"
        )
        .fetchone()
    )
    assert bay, "Baylor Psychology BA not found in data"
    earn = f"${int(round(bay[0])):,}"  # $65,090
    prem_pct = f"+{round(100 * bay[1] / bay[2])}%"  # +87%
    home = HOME.read_text()
    assert earn in home, f"homepage example card missing Baylor earnings {earn}"
    assert prem_pct in home, f"homepage example card missing Baylor premium {prem_pct}"
