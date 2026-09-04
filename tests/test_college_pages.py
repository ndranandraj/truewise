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


def _setup(tmp_path, monkeypatch, register_fixture_slugs):
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
    # Builders resolve slugs strictly from the registry, so register these synthetic schools first.
    register_fixture_slugs()
    bcp.main()
    return tmp_path / "site"


def test_college_page_bakes_the_facts(tmp_path, monkeypatch, register_fixture_slugs):
    site = _setup(tmp_path, monkeypatch, register_fixture_slugs)
    page = site / "college" / "test-state-university" / "index.html"
    assert page.exists(), "college page not generated"
    h = page.read_text()
    # This page is now the full canonical profile (delivery model: static core + JSON island +
    # progressive tail), rendered by build_canonical_profiles.canonical_page.
    # Identity + verdict facts baked into HTML (crawlable without JS).
    assert "Test State University" in h
    assert "Austin, Texas" in h  # city + state identity line
    # Verdict block carries the real counts and the dollar benchmark.
    assert "Of <b>2</b> assessed programs" in h  # 1 pass + 1 fail decided
    assert "<b>1</b> fall short" in h
    assert "about $35,000/yr" in h  # the state high-school-grad benchmark, stated in dollars
    assert "Another <b>1</b> could not be assessed" in h  # the suppressed program is disclosed
    # Coverage label on the program table (honest denominator, not "% have earnings data").
    assert "<b>2 of 3</b> programs could be assessed" in h
    # Net price by income baked in.
    assert "$18,000" in h  # avg net price
    # SEO essentials: canonical + BOTH structured-data types (CollegeOrUniversity carried over from
    # the retired summary page so the cutover does not drop the entity search engines attach to).
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
    # The "vs a high-school grad" column carries the signed earnings premium as crawlable text (the
    # delivery model renders a number, not a chart bar), and the verdict pills mark pass vs fail.
    assert ">vs a high-school grad</th>" in h
    assert "+$35,000" in h and "-$15,000" in h
    assert "tw-verdict--pass" in h and "tw-verdict--fail" in h


def test_state_index_and_national(tmp_path, monkeypatch, register_fixture_slugs):
    site = _setup(tmp_path, monkeypatch, register_fixture_slugs)
    tx = (site / "colleges" / "tx" / "index.html").read_text()
    assert "Colleges in Texas" in tx
    assert "test-state-university" in tx
    nat = (site / "colleges" / "index.html").read_text()
    assert 'href="/colleges/tx/"' in nat


def _school(name, city, npass=3, nfail=1):
    return {"name": name, "city": city, "state": "TX", "n_pass": npass, "n_fail": nfail}


def test_state_index_disambiguates_duplicate_names():
    """Two federal records sharing a name in a state read like a bug; where a name repeats the
    city is folded into the link text (and dropped from the meta so it is not said twice)."""
    from pipeline.build_college_pages import state_index

    rows = [
        ("maestro-college", _school("Maestro College", "Dallas"), None),
        ("maestro-college-tx", _school("Maestro College", "Austin"), None),
        ("rice-university", _school("Rice University", "Houston"), None),
    ]
    html = state_index("TX", rows)
    assert "Maestro College (Dallas)" in html and "Maestro College (Austin)" in html
    # A non-duplicated name keeps a plain link, with its city in the meta line.
    assert ">Rice University</a>" in html and "Houston" in html


def test_national_index_explains_coverage_gap():
    """The directory profiles only schools with a judgeable program; the line states how many
    more are searchable but suppressed, computed from the model so it cannot drift."""
    from pipeline.build_college_pages import national_index

    html = national_index(["TX", "CA"], profiled=4949, searchable=6127)
    assert "4,949" in html and "1,178" in html  # profiled and the searchable-but-suppressed gap
    # No gap sentence when every school in the data is profiled.
    assert "have no full profile" not in national_index(["TX"], profiled=10, searchable=10)
