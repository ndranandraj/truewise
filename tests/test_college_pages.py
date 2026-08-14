"""Test the pre-rendered college/state HTML page generator.

Runs on a synthetic value_check + institutions parquet (no download), exercising the same
build_model + templating that ships. Guards the facts baked into each page and the sitemap.
"""

from __future__ import annotations

import duckdb

import pipeline.build_college_pages as bcp
import pipeline.build_site as bs

VC_COLS = (
    "unitid VARCHAR, inst_name VARCHAR, state VARCHAR, control VARCHAR, cip_code VARCHAR, "
    "cip_desc VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, completers_count INT, "
    "earnings DOUBLE, earnings_horizon VARCHAR, earnings_threshold_state DOUBLE, "
    "earnings_premium_state DOUBLE, debt_median DOUBLE, debt_to_earnings_ratio DOUBLE, "
    "debt_payback_years DOUBLE, value_flag VARCHAR"
)
INST_COLS = (
    "unitid VARCHAR, city VARCHAR, school_url VARCHAR, enrollment INT, net_price_avg DOUBLE, "
    "net_price_0_30k DOUBLE, net_price_30_48k DOUBLE, net_price_48_75k DOUBLE, "
    "net_price_75_110k DOUBLE, net_price_110k_plus DOUBLE, pell_share DOUBLE, "
    "first_gen_share DOUBLE, completion_rate DOUBLE"
)


def _setup(tmp_path, monkeypatch):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({VC_COLS})")
    thr = 35000.0
    rows = [
        # A pass, a fail, and a suppressed program at one school.
        (
            "100",
            "Test State University",
            "TX",
            "Public",
            "5201",
            "Business.",
            "3",
            "Bachelor's Degree",
            120,
            70000.0,
            "4yr_after_completion",
            thr,
            35000.0,
            20000.0,
            0.29,
            0.7,
            "passes_earnings_premium",
        ),
        (
            "100",
            "Test State University",
            "TX",
            "Public",
            "1204",
            "Cosmetology.",
            "1",
            "Certificate",
            40,
            20000.0,
            "4yr_after_completion",
            thr,
            -15000.0,
            8000.0,
            None,
            None,
            "fails_earnings_premium",
        ),
        (
            "100",
            "Test State University",
            "TX",
            "Public",
            "5138",
            "Nursing.",
            "3",
            "Bachelor's Degree",
            None,
            None,
            None,
            thr,
            None,
            None,
            None,
            None,
            "insufficient_data",
        ),
    ]
    con.executemany(f"INSERT INTO vc VALUES ({','.join(['?'] * 17)})", rows)
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")

    con.execute(f"CREATE TABLE inst({INST_COLS})")
    con.execute(
        "INSERT INTO inst VALUES ('100','Austin','http://x',5000,18000,12000,14000,20000,24000,28000,0.4,0.3,0.75)"
    )
    con.execute(f"COPY inst TO '{pq / 'institutions.parquet'}' (FORMAT PARQUET)")

    monkeypatch.setattr(bs, "PARQUET_DIR", pq)
    monkeypatch.setattr(bcp, "SITE", tmp_path / "site")
    bcp.main()
    return tmp_path / "site"


def test_college_page_bakes_the_facts(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    page = site / "college" / "test-state-university" / "index.html"
    assert page.exists(), "college page not generated"
    h = page.read_text()
    # Identity + verdict facts baked into HTML (crawlable without JS).
    assert "Test State University" in h
    assert "Austin, Texas" in h
    assert "2</b> programs with reported earnings" in h  # 1 pass + 1 fail decided
    assert "1</b> fall short" in h
    assert "did not have enough data" in h  # the suppressed program is disclosed, not hidden
    # Net price by income baked in.
    assert "$18,000" in h  # avg net price
    # SEO essentials.
    assert '<link rel="canonical" href="https://truewise.dev/college/test-state-university/"' in h
    assert "CollegeOrUniversity" in h and "BreadcrumbList" in h
    assert "—" not in h  # no em-dash
    # A per-school social card is rendered and the page points its og:image at it.
    assert (
        '<meta property="og:image" content="https://truewise.dev/og/college/test-state-university.png"'
        in h
    )
    card = site / "og" / "college" / "test-state-university.png"
    assert card.exists() and card.stat().st_size > 1000, "per-college OG card missing"
    # The "vs a high-school grad" column renders a diverging bar: the passing program a green
    # bar right of the benchmark line, the failing one a red bar to the left.
    assert ">vs a high-school grad</th>" in h
    assert "class='prem-val pos'" in h and "class='prem-val neg'" in h
    assert "<i class='pos' style='width:" in h and "<i class='neg' style='width:" in h


def test_state_index_and_national(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    tx = (site / "colleges" / "tx" / "index.html").read_text()
    assert "Colleges in Texas" in tx
    assert "test-state-university" in tx
    nat = (site / "colleges" / "index.html").read_text()
    assert 'href="/colleges/tx/"' in nat
