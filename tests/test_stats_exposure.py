"""Test the STATS grad-program exposure computation and finding page.

Runs on a synthetic value_check parquet so the exposure counts are exact and checkable.
"""

from __future__ import annotations

import duckdb

import pipeline.build_stats_exposure as bse

VC_COLS = (
    "unitid VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, cip_desc VARCHAR, "
    "earnings_median_4yr DOUBLE"
)


def _setup(tmp_path, monkeypatch):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE value_check({VC_COLS})")
    # Five master's programs with known 4yr earnings + one undergrad (must be ignored) + one suppressed.
    rows = [
        ("100", "5", "Master's Degree", "Music.", 40000.0),
        ("101", "5", "Master's Degree", "Social Work.", 52000.0),
        ("102", "5", "Master's Degree", "Counseling.", 58000.0),
        ("103", "5", "Master's Degree", "Education.", 61000.0),
        ("104", "5", "Master's Degree", "Business.", 90000.0),
        ("105", "3", "Bachelor's Degree", "Business.", 30000.0),  # undergrad: excluded
        ("106", "5", "Master's Degree", "Art.", None),  # suppressed: not in denominator
    ]
    con.executemany(f"INSERT INTO value_check VALUES ({','.join(['?'] * 5)})", rows)
    con.execute(f"COPY value_check TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")

    monkeypatch.setattr(bse, "PARQUET_DIR", pq)
    monkeypatch.setattr(bse, "SITE", tmp_path / "site")
    return tmp_path / "site"


def test_exposure_counts_are_exact(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    s = bse.compute_exposure(duckdb.connect())
    assert s["total"] == 6  # six graduate rows (undergrad excluded)
    assert s["denom"] == 5  # five with reported 4yr earnings (suppressed dropped)
    curve = {r["benchmark"]: r["n_below"] for r in s["curve"]}
    assert curve[55000] == 2  # 40k, 52k
    assert curve[60000] == 3  # 40k, 52k, 58k
    assert curve[62000] == 4  # 40k, 52k, 58k, 61k
    assert s["band"] == [2, 4]  # below 55k .. below 62k


def test_page_bakes_the_range(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    bse.main()
    h = (site / "findings" / "stats-grad-exposure" / "index.html").read_text()
    assert "2 to 4</b> graduate programs" in h  # the band range, from the data
    assert '<link rel="canonical" href="https://truewise.dev/findings/stats-grad-exposure/"' in h
    assert "not a prediction" in h  # the honesty caveat is present
    assert "—" not in h and "&mdash;" not in h
    idx = (site / "findings" / "index.html").read_text()
    assert 'href="/findings/stats-grad-exposure/"' in idx
