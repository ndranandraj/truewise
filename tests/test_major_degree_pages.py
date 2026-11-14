"""The page per major and degree: its figures, their denominators, and what it says of the federal
test. Runs on a synthetic program table, so no figure here can come from the page being typed."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

import pipeline.build_careers as bc
import pipeline.build_major_degree_pages as mdp
import pipeline.build_majors_pages as bmp
import pipeline.build_sitemap as bsm
from pipeline.degree_levels import DEGREE, degree_path

ROOT = Path(__file__).resolve().parents[1]
EM_DASH = chr(0x2014)
NURSING = "Registered Nursing."
COSMETOLOGY = "Cosmetology and Related Personal Grooming Services."
COLS = (
    "unitid VARCHAR, inst_name VARCHAR, state VARCHAR, cip_code VARCHAR, cip_desc VARCHAR, "
    "credential_level VARCHAR, credential_desc VARCHAR, earnings DOUBLE, earnings_horizon VARCHAR, "
    "value_flag VARCHAR, earnings_threshold_state DOUBLE, debt_median DOUBLE, "
    "completers_count DOUBLE"
)
PASS, FAIL, NONE = "passes_earnings_premium", "fails_earnings_premium", "insufficient_data"
Y4, Y1 = "4yr_after_completion", "1yr_after_completion"


def _rows() -> list[tuple]:
    def row(unitid, cip, desc, lvl, cred, earn, horizon, flag, line, debt, done):
        return (
            str(unitid),
            f"College {unitid}",
            "TX",
            cip,
            desc,
            lvl,
            cred,
            earn,
            horizon,
            flag,
            line,
            debt,
            done,
        )

    b = ("5138", NURSING, "3", "Bachelor's Degree")
    m = ("5138", NURSING, "5", "Master's Degree")
    c = ("1204", COSMETOLOGY, "1", "Undergraduate Certificate or Diploma")
    return [
        # Bachelor's: six assessed (median 82,500), one with earnings and no benchmark, two with none.
        row(101, *b, 80000.0, Y4, FAIL, 40000.0, 20000.0, 50.0),
        row(102, *b, 81000.0, Y4, PASS, 40000.0, 22000.0, 300.0),
        row(103, *b, 82000.0, Y4, PASS, 40000.0, 24000.0, 300.0),
        row(104, *b, 83000.0, Y4, PASS, 40000.0, 26000.0, 10.0),
        row(105, *b, 84000.0, Y4, PASS, 40000.0, None, None),
        row(106, *b, 85000.0, Y1, PASS, 40000.0, None, 5.0),
        row(107, *b, 70000.0, Y4, NONE, None, None, 400.0),
        row(108, *b, None, None, NONE, None, None, 20.0),
        row(109, *b, None, None, NONE, None, None, None),
        # Master's: five assessed, all above the line, none reporting debt.
        *[
            row(201 + i, *m, 100000.0 + 1000 * i, Y4, PASS, 40000.0, None, 10.0 + i)
            for i in range(5)
        ],
        # Cosmetology certificate: four of five below the line, all on 1-year earnings.
        *[
            row(301 + i, *c, 20000.0 + 1000 * i, Y1, FAIL, 30000.0, 8000.0, 40.0 - i)
            for i in range(4)
        ],
        row(305, *c, 35000.0, Y1, PASS, 30000.0, 9000.0, 1.0),
    ]


@pytest.fixture
def site(tmp_path, monkeypatch):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({COLS})")
    con.executemany(f"INSERT INTO vc VALUES ({','.join(['?'] * 13)})", _rows())
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")
    out = tmp_path / "site"
    monkeypatch.setattr(bc, "PARQUET_DIR", pq)
    monkeypatch.setattr(mdp, "SITE", out)
    monkeypatch.setattr(bmp, "SITE", out)
    monkeypatch.setattr(bsm, "SITE", out)
    # Only one college has a profile, so a link to any other would be a link to nothing.
    monkeypatch.setattr(mdp, "profile_slugs", lambda con: {"102": "college-102"})
    mdp.main()
    return out


def _page(site, major: str, degree: str) -> str:
    return (site / "majors" / major / degree / "index.html").read_text(encoding="utf-8")


def _text(markup: str) -> str:
    markup = re.sub(r"<script.*?</script>|<style.*?</style>", " ", markup, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", markup).replace("&rsquo;", "'")
    return re.sub(r"\s+", " ", text)


def test_one_page_per_major_and_degree_at_its_own_address(site):
    pages = sorted(
        p.parent.relative_to(site).as_posix() for p in site.glob("majors/*/*/index.html")
    )
    assert pages == [
        "majors/cosmetology-and-related-personal-grooming-services/certificate",
        "majors/registered-nursing/bachelors",
        "majors/registered-nursing/masters",
    ]
    html = _page(site, "registered-nursing", "bachelors")
    assert (
        '<link rel="canonical" href="https://truewise.dev/majors/registered-nursing/bachelors/"'
        in html
    )
    # The site's default card: the major's card carries another degree's figure.
    assert '<meta property="og:image" content="https://truewise.dev/og.png"' in html


def test_the_median_keeps_its_population_coverage_and_horizon_in_the_same_box(site):
    html = _page(site, "registered-nursing", "bachelors")
    box = _text(html.split('<div class="kf"', 1)[1].split("</div>\n\n", 1)[0])
    assert "$82,500 a year, the middle of 6 bachelor's programs" in box
    assert "6 of the 9 bachelor's programs ED lists in this field could be assessed." in box
    assert (
        "The other 3: 1 with earnings but no state benchmark and 2 with no earnings published."
        in box
    )
    assert "1 of the 6 uses 1-year earnings, an earlier career stage" in box
    for block in re.findall(r"<details.*?</details>", html, flags=re.S):
        assert "1-year" not in block and "could be assessed" not in block


def test_range_and_debt_say_what_they_rest_on_and_a_missing_one_says_why(site):
    text = _text(_page(site, "registered-nursing", "bachelors"))
    assert "Middle half of programs $81,250 to $83,750" in text
    assert "$23,000 Federal loans only. The middle of the 4 programs that report it." in text
    masters = _text(_page(site, "registered-nursing", "masters"))
    assert "not reported No program in this group reports a debt figure." in masters
    assert "5 of the 5 master's programs ED lists in this field could be assessed." in masters
    assert "All are measured four years after finishing." in masters
    assert "The other" not in masters.split("could be assessed.", 1)[1].split("Middle half", 1)[0]


def test_an_undergraduate_page_names_the_federal_comparison_as_truewises_calculation(site):
    text = _text(_page(site, "registered-nursing", "bachelors"))
    assert "In 5 of the 6 assessed programs, graduates earned more than" in text
    assert "In 1, they earned less." in text
    assert "the comparison the federal earnings test makes for undergraduate programs" in text
    assert "not the Department of Education's result" in text
    assert "not that test" not in text


def test_a_graduate_page_never_calls_the_high_school_comparison_the_federal_test(site):
    text = _text(_page(site, "registered-nursing", "masters"))
    assert "In all 5 assessed programs, graduates earned more than" in text
    assert "These are graduate programs." in text
    assert "compares graduate programs with bachelor's degree holders" in text
    assert "So this comparison is not that test." in text
    assert "This is the comparison the federal earnings test makes" not in text


def test_the_tipped_jobs_note_is_beside_the_cosmetology_count_and_nowhere_else(site):
    html = _page(site, "cosmetology-and-related-personal-grooming-services", "certificate")
    line = html.split('<section id="line"', 1)[1].split("</section>", 1)[0]
    assert "In 1 of the 5 assessed programs" in _text(line)
    caveat = _text(re.search(r'<p class="caveat">.*?</p>', line, flags=re.S).group(0))
    assert (
        "holds programs for tipped jobs, cosmetology among them, out of its first rounds" in caveat
    )
    assert "does not pass or fail them" in caveat
    assert 'href="/earnings-test/#held"' in line
    assert "All use 1-year earnings, an earlier career stage." in _text(html)
    assert "tipped" not in _page(site, "registered-nursing", "bachelors")


def test_a_group_where_no_program_clears_the_line_says_so():
    m = {"decided": 7, "n_pass": 0, "n_fail": 7}
    assert "In all 7 assessed programs, graduates earned less than" in mdp.against_line(
        m, "5138", "2"
    )


def test_colleges_are_ordered_by_completions_and_each_row_says_what_is_missing(site):
    html = _page(site, "registered-nursing", "bachelors")
    section = html.split('<section id="colleges"', 1)[1].split("</section>", 1)[0]
    assert "The 7 colleges where the most students complete" in _text(section)
    assert "of 7 that report completions" in _text(section)
    rows = [_text(r) for r in re.findall(r"<tr><td>.*?</tr>", section, flags=re.S)]
    # 102 and 103 both report 300: the lower UNITID comes first, in every build.
    assert [r.split()[1] for r in rows] == ["107", "102", "103", "101", "108", "104", "106"]
    assert "$70,000 no state benchmark 400" in rows[0]
    assert "$81,000 +$41,000 300" in rows[1]
    assert "not published not assessed 20" in rows[4]
    assert "$85,000 1-year earnings +$45,000 5" in rows[6]
    # Linked only where a profile exists.
    assert section.count('href="/college/') == 1 and 'href="/college/college-102/"' in section
    below = _page(site, "cosmetology-and-related-personal-grooming-services", "certificate")
    assert "-$10,000" in below


def test_the_other_degree_levels_are_linked_and_this_one_is_marked(site):
    html = _page(site, "registered-nursing", "bachelors")
    section = html.split('<section id="degrees"', 1)[1].split("</section>", 1)[0]
    assert '<a href="/majors/registered-nursing/masters/">' in section
    assert '<a href="/majors/registered-nursing/bachelors/" aria-current="page">' in section
    assert section.count('class="md-cur"') == 1 and "This page" in section


def test_the_major_page_links_each_degree_row_to_its_page(site):
    creds = [f for f in bc.build_fields(duckdb.connect()) if f["cip"] == "5138"]
    html = bmp.major_page(
        "5138", "Registered Nursing", "Health Professions", creds, "registered-nursing"
    )
    for f in creds:
        path = degree_path("registered-nursing", f["cred"])
        assert f'<a href="{path}">' in html
        assert (site / path.strip("/") / "index.html").exists(), (
            "a link to a page that is not built"
        )


def test_a_page_whose_median_differs_from_the_careers_figure_stops_the_build(site):
    con = duckdb.connect()
    fields = [f for f in bc.build_fields(con) if f["cip"] == "5138" and f["cred"] == "3"]
    rows = mdp.all_programs(con)[("5138", "3")]
    wrong = dict(fields[0], med=fields[0]["med"] + 1)
    with pytest.raises(SystemExit, match="differ from build_fields"):
        mdp.degree_page(wrong, fields, rows, "registered-nursing", {})


def test_a_degree_level_without_a_name_and_address_stops_the_build(site, monkeypatch):
    real = bc.build_fields

    def with_unknown(con):
        fields = real(con)
        return fields + [dict(fields[0], cred="42")]

    monkeypatch.setattr(bc, "build_fields", with_unknown)
    with pytest.raises(SystemExit, match="degree levels with no entry"):
        mdp.main()


def test_titles_lead_with_the_degree_and_field_and_descriptions_fit_a_search_result(site):
    long_name = "Electrical/Electronics Maintenance and Repair Technologies/Technicians"
    for f in (
        {"cip": "5138", "name": "Registered Nursing", "cred": "3", "med": 84253, "programs": 903},
        {"cip": "4701", "name": long_name, "cred": "1", "med": 43812, "programs": 1},
    ):
        title, desc = mdp.title_and_desc(f)
        assert title.startswith(DEGREE[f["cred"]].title + " in ")
        assert "median" in title, "a figure in a title keeps the word that says what it is"
        assert len(desc) <= 155, "a longer description is cut in a search result"
        assert "median" in desc
    assert mdp.title_and_desc(
        {"cip": "5138", "name": "Registered Nursing", "cred": "3", "med": 84253, "programs": 903}
    )[0] == ("Bachelor's in Nursing: what graduates earn ($84,253 median)")
    assert (
        "(1 program)"
        in mdp.title_and_desc(
            {"cip": "4701", "name": long_name, "cred": "1", "med": 43812, "programs": 1}
        )[1]
    )


def test_occupations_are_labelled_as_field_wide_and_a_negative_zero_is_not_printed():
    demand = {
        "growth_pct": -0.0,
        "annual_openings": None,
        "vintage": {"oews": "May 2025", "ep": "2025-35"},
        "occupations": [
            {"title": "Registered Nurses", "wage": 97550.0, "growth": None, "openings": 1800.0}
        ],
    }
    text = _text(mdp.outlook({"demand": demand}))
    assert "growth of +0% from 2025 to 2035" in text and "-0%" not in text
    assert "about not published openings a year" in text
    assert "matched to the field at every degree level, not to this degree" in text
    assert "Registered Nurses $97,550 not published 1,800" in text
    assert mdp.outlook({}) == ""


def test_the_pages_follow_the_writing_rules(site):
    for page in site.glob("majors/*/*/index.html"):
        html = page.read_text(encoding="utf-8")
        assert EM_DASH not in html and "&mdash;" not in html
        assert not re.search(r"\bn/a\b", _text(html), flags=re.I)
        assert "Not affiliated with the U.S. Department of Education" in html


def test_the_sitemap_lists_each_page_once_in_its_own_file(site):
    bmp.main()  # the major pages these sit under
    bsm.main()
    index = (site / "sitemap.xml").read_text()
    assert "https://truewise.dev/sitemap-major-degrees.xml" in index
    own = (site / "sitemap-major-degrees.xml").read_text()
    assert own.count("<loc>") == 3
    assert "<loc>https://truewise.dev/majors/registered-nursing/masters/</loc>" in own
    majors = (site / "sitemap-majors.xml").read_text()
    assert "/bachelors/" not in majors and "/majors/registered-nursing/</loc>" in majors
    everywhere = "".join(p.read_text() for p in site.glob("sitemap-*.xml"))
    assert everywhere.count("/majors/registered-nursing/bachelors/</loc>") == 1


def test_the_builder_runs_in_every_build_and_the_pages_are_in_the_layout_check():
    for name in (".github/workflows/deploy.yml", "preview-build.sh", "Makefile"):
        text = (ROOT / name).read_text()
        assert text.index("pipeline.build_major_degree_pages") > text.index(
            "pipeline.build_majors_pages"
        ), f"{name}: the degree pages are built after the major pages they sit under"
    probe = (ROOT / "tests" / "layout_probe.js").read_text()
    assert probe.count('/bachelors/", kind: "static"') == 1
    assert '/certificate/", kind: "static"' in probe, "a page family outside the layout check"


def test_every_degree_level_has_a_distinct_address():
    slugs = [level.slug for level in DEGREE.values()]
    assert len(set(slugs)) == len(slugs)
    assert degree_path("x", "3") == "/majors/x/bachelors/" and degree_path("x", "42") is None
