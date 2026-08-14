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
    # Reported-earnings split: has earnings vs of-those-judgeable (the precise wording fix).
    has_earn, no_bench = con.execute(
        "SELECT count(*) FILTER (WHERE earnings IS NOT NULL), "
        "count(*) FILTER (WHERE earnings IS NOT NULL AND earnings_threshold_state IS NULL) FROM v"
    ).fetchone()  # 62,902 and 2,700

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
    # Reported-earnings wording fix: both the has-earnings and unjudgeable counts must be exact.
    assert f"{has_earn:,}" in meth, f"methodology missing has-earnings count {has_earn:,}"
    assert f"{no_bench:,}" in meth, f"methodology missing no-benchmark count {no_bench:,}"


def test_home_distribution_chart_matches_data():
    """The homepage histogram is generated from the parquet by build_home_chart. Recompute the
    seven bucket counts, the fall-short total, and the judged total here, and assert each appears
    in the committed SVG, so the chart can never drift from the data it claims to show."""
    from pipeline.build_home_chart import EDGES, LABELS

    con = _con()
    case = (
        "CASE "
        + " ".join(
            f"WHEN pct >= {EDGES[i]} AND pct < {EDGES[i + 1]} THEN {i}" for i in range(len(LABELS))
        )
        + " END"
    )
    rows = con.execute(
        f"""
        WITH d AS (
          SELECT earnings_premium_state * 100.0 / earnings_threshold_state AS pct FROM v
          WHERE value_flag IN ('passes_earnings_premium','fails_earnings_premium')
            AND earnings_threshold_state IS NOT NULL
        )
        SELECT {case} AS b, count(*) FROM d GROUP BY b ORDER BY b
        """
    ).fetchall()
    counts = [0] * len(LABELS)
    for b, n in rows:
        counts[b] = n
    total = sum(counts)

    home = HOME.read_text()
    assert home.count("HOME_CHART_START") == 1 and home.count("HOME_CHART_END") == 1
    for c in counts:
        assert f'data-count="{c}"' in home, f"home chart missing bar for count {c}"
    # The fall-short bucket and judged total must be spelled out in the accessible description.
    assert f"{counts[0]:,}" in home and f"{total:,}" in home


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
