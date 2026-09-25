"""Test the /majors/ field-page generator and the filesystem sitemap builder.

Runs on a synthetic value_check parquet (no download), exercising the shared build_fields
plus the major-page templating and the sitemap scan.
"""

from __future__ import annotations

import duckdb

import pipeline.build_careers as bc
import pipeline.build_majors_pages as bmp
import pipeline.build_sitemap as bsm

VC_COLS = (
    "unitid VARCHAR, cip_code VARCHAR, cip_desc VARCHAR, credential_level VARCHAR, "
    "credential_desc VARCHAR, earnings DOUBLE, value_flag VARCHAR"
)


def _setup(tmp_path, monkeypatch):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({VC_COLS})")
    rows = []
    # Two credentials for one major (CIP 5138 Nursing), >=5 programs each so they report.
    for lvl, cred, base in (("3", "Bachelor's Degree", 80000), ("2", "Associate's Degree", 70000)):
        for i in range(6):
            flag = "fails_earnings_premium" if i == 0 else "passes_earnings_premium"
            rows.append(
                (
                    str(100 + i if lvl == "3" else 200 + i),
                    "5138",
                    "Registered Nursing.",
                    lvl,
                    cred,
                    float(base + i * 500),
                    flag,
                )
            )
    con.executemany(f"INSERT INTO vc VALUES ({','.join(['?'] * 7)})", rows)
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")

    monkeypatch.setattr(bc, "PARQUET_DIR", pq)
    monkeypatch.setattr(bmp, "SITE", tmp_path / "site")
    monkeypatch.setattr(bsm, "SITE", tmp_path / "site")
    bmp.main()
    return tmp_path / "site"


def test_major_page_bakes_degree_ladder(tmp_path, monkeypatch):
    site = _setup(tmp_path, monkeypatch)
    page = site / "majors" / "registered-nursing" / "index.html"
    assert page.exists(), "major page not generated"
    h = page.read_text()
    assert "Registered Nursing" in h
    assert "Median earnings by degree level" in h
    assert "Bachelor" in h and "Associate" in h  # both credentials in the ladder
    # The earnings-range chart renders: a labelled figure with a median dot and a p25-p75 band.
    assert 'class="ladder-chart ladder--wide"' in h and 'class="ladder-chart ladder--narrow"' in h
    assert '<title id="ladderT">' in h and '<title id="ladderTM">' in h
    # No chart text under 12 user units: the narrow variant is drawn at phone width, so 12 renders
    # at about 12px (the single 640-wide chart put 10 and 11 at 5.5 to 6px on a phone).
    import re

    sizes = [int(x) for x in re.findall(r'<text[^>]*font-size="(\d+)"', h)]
    assert sizes and min(sizes) >= 12, sizes
    assert "<circle" in h and 'fill="#e6eee7"' in h  # median dot + middle-half band
    assert '<link rel="canonical" href="https://truewise.dev/majors/registered-nursing/"' in h
    assert "BreadcrumbList" in h
    assert "—" not in h and "&mdash;" not in h
    # A per-major social card is rendered and the page points its og:image at it (not the generic one).
    assert (
        '<meta property="og:image" content="https://truewise.dev/og/majors/registered-nursing.png"'
        in h
    )
    card = site / "og" / "majors" / "registered-nursing.png"
    assert card.exists() and card.stat().st_size > 1000, "per-major OG card missing"
    # Index lists the major.
    idx = (site / "majors" / "index.html").read_text()
    assert 'href="/majors/registered-nursing/"' in idx


def test_sitemap_includes_majors(tmp_path, monkeypatch):
    """/sitemap.xml is a sitemap INDEX now, so the URLs live one level down.

    A single 6,548-URL file was valid but undiagnosable: the September baseline showed 4,930
    indexed against 6,548 submitted with nothing saying which families the missing 1,618 were in.
    The index URL itself is unchanged, so what is submitted in Search Console keeps working.
    """
    site = _setup(tmp_path, monkeypatch)
    bsm.main()
    index = (site / "sitemap.xml").read_text()
    assert "<sitemapindex" in index, "/sitemap.xml should be an index"
    assert "https://truewise.dev/sitemap-majors.xml" in index

    majors = (site / "sitemap-majors.xml").read_text()
    assert "https://truewise.dev/majors/registered-nursing/" in majors
    # The /majors/ hub is a core page, not a major, and must appear exactly once across all files.
    everywhere = "".join(p.read_text() for p in site.glob("sitemap-*.xml"))
    assert everywhere.count("<loc>https://truewise.dev/majors/</loc>") == 1, (
        "a URL in two sitemaps makes the per-family counts disagree with reality"
    )
