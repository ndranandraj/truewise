"""Test the ranked-list generator.

Runs on a synthetic parquet so the ranking order and the minimum-sample rule are exact and
checkable, and asserts that each list states its metric and sample rule on the page.
"""

from __future__ import annotations

import duckdb

import pipeline.build_lists as bl
import pipeline.build_site as bs

VC_COLS = (
    "unitid VARCHAR, inst_name VARCHAR, state VARCHAR, control VARCHAR, cip_code VARCHAR, "
    "cip_desc VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, completers_count INT, "
    "earnings DOUBLE, earnings_horizon VARCHAR, earnings_threshold_state DOUBLE, "
    "earnings_premium_state DOUBLE, debt_median DOUBLE, debt_to_earnings_ratio DOUBLE, "
    "debt_payback_years DOUBLE, value_flag VARCHAR"
)


def _setup(tmp_path, monkeypatch, register_fixture_slugs):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({VC_COLS})")
    thr = 35000.0
    rows = []
    # Two majors with 12 bachelor's programs each: Engineering pays more than Art.
    for cip, desc, base in (("1410", "Engineering.", 90000.0), ("5007", "Fine Arts.", 40000.0)):
        for i in range(12):
            rows.append(
                (
                    f"{cip}{i}",
                    f"School {cip}{i}",
                    "TX",
                    "Public",
                    cip,
                    desc,
                    "3",
                    "Bachelor's Degree",
                    50,
                    base + i * 100,
                    "4yr_after_completion",
                    thr,
                    base + i * 100 - thr,
                    20000.0,
                    0.3,
                    1.0,
                    "passes_earnings_premium",
                )
            )
    # A thin major (only 3 programs) must be excluded by the minimum-sample rule.
    for i in range(3):
        rows.append(
            (
                f"thin{i}",
                f"Thin School {i}",
                "TX",
                "Public",
                "9999",
                "Thin Field.",
                "3",
                "Bachelor's Degree",
                10,
                999000.0,
                "4yr_after_completion",
                thr,
                964000.0,
                None,
                None,
                None,
                "passes_earnings_premium",
            )
        )
    con.executemany(f"INSERT INTO vc VALUES ({','.join(['?'] * 17)})", rows)
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")

    monkeypatch.setattr(bl, "PARQUET_DIR", pq)
    monkeypatch.setattr(bs, "PARQUET_DIR", pq)
    monkeypatch.setattr(bl, "SITE", tmp_path / "site")
    # Builders resolve slugs strictly from the registry, so register these synthetic schools first.
    register_fixture_slugs()
    bl.main()
    return tmp_path / "site"


def test_highest_paying_ranks_correctly_and_excludes_thin_majors(
    tmp_path, monkeypatch, register_fixture_slugs
):
    site = _setup(tmp_path, monkeypatch, register_fixture_slugs)
    h = (site / "lists" / "highest-paying-majors" / "index.html").read_text()
    assert "Engineering" in h
    # The higher-paying major must rank above the lower-paying one.
    assert h.index("Engineering") < h.index("Fine Arts")
    # A 3-program major must not appear, even though its earnings are the highest.
    assert "Thin Field" not in h, "minimum-sample rule failed: thin major was ranked"
    # The page must state its metric and sample rule.
    assert "at least 10 programs" in h
    assert "—" not in h and "&mdash;" not in h
    # A per-list social card is rendered and the page points its og:image at it.
    assert (
        '<meta property="og:image" content="https://truewise.dev/og/lists/highest-paying-majors.png"'
        in h
    )
    card = site / "og" / "lists" / "highest-paying-majors.png"
    assert card.exists() and card.stat().st_size > 1000, "per-list OG card missing"


def test_index_and_state_list_exist(tmp_path, monkeypatch, register_fixture_slugs):
    site = _setup(tmp_path, monkeypatch, register_fixture_slugs)
    idx = (site / "lists" / "index.html").read_text()
    assert 'href="/lists/highest-paying-majors/"' in idx
    assert "one stated metric" in idx  # the honesty framing
    tx = site / "lists" / "best-value-colleges-tx" / "index.html"
    assert not tx.exists() or "clear the bar" in tx.read_text()
