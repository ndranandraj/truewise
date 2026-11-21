"""The profile's "About the college" and "Colleges to compare" sections (Prototype N).

What these guard, in the order a reader would be misled:
  * a figure without the population and year it describes, or a missing one shown as a value;
  * a completion rate without the number of students it rests on (923 of 5,058 rest on fewer
    than 30);
  * a year carried over to a release it does not describe;
  * a list of colleges that is not the list the printed rule gives, or that changes between builds;
  * a count on one profile that disagrees with the headline of the profile it links to.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pytest

import analysis.validate as validate
import pipeline.build_college_pages as bcp
import pipeline.build_site as bs
import pipeline.profile_basics as pb
import pipeline.profile_layout as pl
from pipeline.build_canonical_profiles import SCORECARD_RELEASE, canonical_page

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)
JUNE = pb.Years("fall 2024", "2023-24", "2018-19", "2021-22")
FULL = pb.Basics("www.example.edu/", 14785, 0.1196, 0.7999, 3363, "four_year", 3)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", html)).replace("&rsquo;", "’").strip()


def _facts(html: str) -> dict[str, tuple[str, str]]:
    """label -> (figure, note) for each fact in a page's About section."""
    start = html.index('<section id="about"')
    about = html[start : html.index("</section>", start)]
    out = {}
    for label, fig, note in re.findall(
        r"<dt>([^<]*)</dt><dd><span class=\"basics__fig[^\"]*\">(.*?)</span>"
        r"<span class=\"basics__note\">(.*?)</span></dd>",
        about,
        re.S,
    ):
        out[label] = (_text(fig), _text(note))
    return out


# --- Percentages and years ---------------------------------------------------------------------


def test_a_percentage_is_rounded_once_half_up_and_never_to_all_or_none():
    assert pb.pct(0.1645) == "16%"  # rounded to 0.165 first, this read 17%
    assert pb.pct(0.125) == "13%"  # half up, as Compare's Math.round gives
    assert pb.pct(0.7999) == "80%"
    assert pb.pct(1.0) == "100%" and pb.pct(0.0) == "0%"
    # 199 of 200 is not everyone, and 1 of 400 is not no one.
    assert pb.pct(0.995) == "99%"
    assert pb.pct(0.0025) == "1%"


def test_the_years_belong_to_one_release_and_an_unknown_release_stops_the_build():
    assert pb.years_for("2026-06-10") == JUNE
    # ED refreshed Pell and completion on 15 October; enrollment stayed at fall 2024.
    assert pb.years_for("2026-11-02") == pb.Years("fall 2024", "2024-25", "2019-20", "2022-23")
    with pytest.raises(SystemExit, match="2027-01-15"):
        pb.years_for("2027-01-15")
    # The release this branch builds has its years.
    assert SCORECARD_RELEASE in pb.YEARS


# --- About the college -------------------------------------------------------------------------


def test_each_fact_keeps_its_population_and_year_beside_it():
    html = pb.about_section(FULL, JUNE, "2026-06-10")
    facts = _facts(html)
    assert list(facts) == [
        "Undergraduates",
        "Students with a Pell grant",
        "Completion rate",
        "Website",
    ]
    assert facts["Undergraduates"] == (
        "14,785",
        "Degree-seeking undergraduates enrolled in fall 2024.",
    )
    assert facts["Students with a Pell grant"] == (
        "12%",
        "Of undergraduates in 2023-24. Pell grants are federal aid for students from "
        "lower-income families.",
    )
    assert facts["Completion rate"] == (
        "80%",
        "Of the 3,363 first-time, full-time students who started in 2018-19, the share who "
        "finished within 150% of the normal time for their program (for example, six years for a "
        "bachelor’s degree). Transfer and part-time students are not counted.",
    )
    assert facts["Website"] == (
        "example.edu",
        "As the college reported it to the Department of Education.",
    )
    assert '<a class="basics__url" href="https://www.example.edu/" rel="noopener">' in html
    # It describes the whole college, says so, and names its release.
    assert "These describe the college as a whole, not any one program." in html
    assert "release 2026-06-10" in html
    # Nothing that changes a figure's meaning is behind a toggle.
    assert "<details" not in html
    assert EM_DASH not in html and "&mdash;" not in html


def test_the_cohort_year_follows_the_kind_of_rate_the_college_reports():
    two_year = FULL._replace(basis="less_than_four_year", cohort=2455, completion=0.202)
    note = _facts(pb.about_section(two_year, JUNE, "2026-06-10"))["Completion rate"][1]
    assert "Of the 2,455 first-time, full-time students who started in 2021-22" in note
    assert "(for example, three years for a two-year program)" in note
    # The next release moves both cohorts on by a year.
    nov = pb.years_for("2026-11-02")
    assert (
        "started in 2022-23"
        in _facts(pb.about_section(two_year, nov, "2026-11-02"))["Completion rate"][1]
    )
    assert (
        "started in 2019-20"
        in _facts(pb.about_section(FULL, nov, "2026-11-02"))["Completion rate"][1]
    )


def test_a_rate_on_a_small_group_says_how_far_one_student_moves_it():
    def note(cohort, rate=1.0):
        b = FULL._replace(cohort=cohort, completion=rate)
        return _facts(pb.about_section(b, JUNE, "2026-06-10"))["Completion rate"]

    fig, text = note(2)
    assert fig == "100%"
    assert text.startswith("Of the 2 first-time, full-time students who started in 2018-19")
    assert text.endswith(
        "A small group: with 2 students, one student moves this figure by 50 points."
    )
    # 100 / 29 is 3.4: "about", not a false exactness.
    assert note(29, 0.5)[1].endswith("one student moves this figure by about 3 points.")
    assert note(25, 0.36)[1].endswith("one student moves this figure by 4 points.")
    assert note(1)[1].endswith("with 1 student, one student moves this figure by 100 points.")
    assert "Of the 1 first-time, full-time student who started" in note(1)[1]
    # At ED's own line of 30 the sentence stops.
    assert "A small group" not in note(30, 0.5)[1]


def test_a_rate_is_never_printed_without_the_students_it_rests_on():
    with pytest.raises(ValueError, match="cohort"):
        pb.about_section(FULL._replace(cohort=None), JUNE, "2026-06-10")
    with pytest.raises(ValueError, match="cohort"):
        pb.about_section(FULL._replace(basis=None), JUNE, "2026-06-10")


def test_a_missing_figure_says_not_published_and_why_never_a_value():
    empty = pb.Basics(None, None, None, None, None, None, 4)
    html = pb.about_section(empty, JUNE, "2026-06-10")
    facts = _facts(html)
    assert {fig for fig, _ in facts.values()} == {"not published"}
    assert facts["Undergraduates"][1] == "ED published no undergraduate count for this college."
    assert facts["Students with a Pell grant"][1] == "ED published no Pell figure for this college."
    assert facts["Completion rate"][1] == (
        "ED published no completion rate. It follows first-time, full-time students only, and a "
        "college with none to follow has no rate."
    )
    assert facts["Website"][1] == "ED published no web address for this college."
    assert html.count("basics__fig--none") == 4
    # Listed in ED's file, so the page does not claim otherwise.
    assert "does not list this college" not in html
    # A reported zero is a figure, not a gap.
    zero = _facts(pb.about_section(empty._replace(enrollment=0, pell=0.0), JUNE, "2026-06-10"))
    assert zero["Undergraduates"][0] == "0" and zero["Students with a Pell grant"][0] == "0%"


def test_a_college_missing_from_the_institution_file_says_so_once():
    html = pb.about_section(None, JUNE, "2026-06-10")
    assert (
        '<p class="basics__lead">ED&rsquo;s institution file does not list this college, so none '
        "of these figures is published.</p>" in html
    )
    assert {fig for fig, _ in _facts(html).values()} == {"not published"}


def test_only_a_web_address_a_reader_can_follow_becomes_a_link(tmp_path):
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE inst(unitid VARCHAR, school_url VARCHAR, enrollment DOUBLE,
           pell_share DOUBLE, completion_rate DOUBLE, completion_cohort INTEGER,
           completion_basis VARCHAR, predominant_degree INTEGER)"""
    )
    urls = {
        "1": "https://www.ccad.edu/",
        "2": "www.southuniversity.edu/tampa#location=Tampa, FL",
        "3": "https://imbeautyschool@gmail.com/",  # an email address: it would open gmail.com
        "4": "NA",
        "5": None,
    }
    con.executemany(
        "INSERT INTO inst VALUES (?, ?, 10, 0.5, NULL, NULL, NULL, 1)", list(urls.items())
    )
    path = tmp_path / "institutions.parquet"
    con.execute(f"COPY inst TO '{path}' (FORMAT PARQUET)")
    got = pb.load(duckdb.connect(), path)
    assert got["1"].url == "https://www.ccad.edu/"
    assert got["2"].url == "www.southuniversity.edu/tampa"
    assert got["3"].url is None and got["4"].url is None and got["5"].url is None
    site = _facts(pb.about_section(got["2"], JUNE, "2026-06-10"))["Website"]
    assert site[0] == "southuniversity.edu/tampa"
    assert 'href="https://www.southuniversity.edu/tampa"' in pb.about_section(
        got["2"], JUNE, "2026-06-10"
    )
    assert _facts(pb.about_section(got["3"], JUNE, "2026-06-10"))["Website"][0] == "not published"


def test_an_institutions_file_without_the_new_columns_stops_the_build(tmp_path):
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE inst(unitid VARCHAR, school_url VARCHAR, enrollment DOUBLE,
           pell_share DOUBLE, completion_rate DOUBLE)"""
    )
    con.execute("INSERT INTO inst VALUES ('1', 'x.edu', 10, 0.5, 0.9)")
    path = tmp_path / "institutions.parquet"
    con.execute(f"COPY inst TO '{path}' (FORMAT PARQUET)")
    with pytest.raises(SystemExit, match="completion_cohort, completion_basis, predominant_degree"):
        pb.load(duckdb.connect(), path)


# --- Colleges to compare -----------------------------------------------------------------------


def _peer(unitid, name, enrollment, **kw):
    base = {
        "slug": name.lower().replace(" ", "-"),
        "state": "TX",
        "control": "Public",
        "degree": 3,
        "above": 3,
        "assessed": 4,
    }
    base.update(kw)
    return pb.Peer(unitid=unitid, name=name, enrollment=enrollment, **base)


def test_the_list_is_the_rule_same_state_type_and_credential_nearest_in_size():
    index = pb.PeerIndex(
        [
            _peer("1", "Home College", 1000),
            _peer("2", "Near College", 1100),
            _peer("3", "Far College", 9000),
            _peer("4", "Other State", 1000, state="OK"),
            _peer("5", "Other Type", 1000, control="Private, nonprofit"),
            _peer("6", "Other Credential", 1000, degree=2),
            _peer("7", "No Size", None),
        ]
    )
    case, shown, total = index.nearest("1")
    assert (case, [p.name for p in shown], total) == ("ok", ["Near College", "Far College"], 2)


def test_at_most_five_are_shown_and_equal_distances_have_one_order():
    colleges = [_peer("10", "Home College", 1000)]
    # Two colleges 50 away on either side, with the same name bar case, then five more.
    colleges += [_peer("12", "twin college", 1050), _peer("11", "Twin College", 950)]
    colleges += [_peer(str(20 + i), f"College {i}", 1100 + 100 * i) for i in range(5)]
    forward = pb.PeerIndex(colleges).nearest("10")
    backward = pb.PeerIndex(list(reversed(colleges))).nearest("10")
    assert forward == backward, "the order of the input decided the list"
    case, shown, total = forward
    assert total == 7 and len(shown) == pb.MAX_PEERS == 5
    # Same distance, same name ignoring case: the federal ID decides.
    assert [p.unitid for p in shown[:2]] == ["11", "12"]
    assert [p.name for p in shown[2:]] == ["College 0", "College 1", "College 2"]


def test_where_the_rule_cannot_apply_the_section_says_why_and_gives_a_next_step():
    home = _peer("1", "Home College", 1000)
    cases = {
        "graduate": (home._replace(degree=4), "awards graduate degrees only"),
        "unclassified": (home._replace(degree=0), "does not classify"),
        "unlisted": (home._replace(degree=None, enrollment=None), "does not list this college"),
        "no-size": (home._replace(enrollment=None), "enrollment is not published"),
        "none": (home, "No other public college in Texas awards mostly bachelor’s degrees"),
        "no-state": (home._replace(state="ZZ"), "does not report this college’s state"),
    }
    for want, (college, phrase) in cases.items():
        index = pb.PeerIndex([college, _peer("2", "Elsewhere", 1000, state="OK")])
        assert index.nearest("1")[0] == want
        html = pb.compare_section("1", index, JUNE)
        assert phrase in _text(html), want
        assert "<table" not in html
        # No profile ends without somewhere to go.
        link = '<a href="/colleges/">' if want == "no-state" else '<a href="/colleges/tx/">'
        assert link in html, want
    # A college whose type ED does not give cannot be matched on type.
    assert pb.PeerIndex([home._replace(control=None)]).nearest("1")[0] == "unclassified"


def test_the_section_prints_its_rule_and_each_row_its_count_and_a_side_by_side_link():
    others = [
        _peer("2", "Near College", 1100, above=32, assessed=32),
        _peer("3", "Far College", 9000, above=0, assessed=0),
    ]
    index = pb.PeerIndex([_peer("1", "Home College", 1000), *others])
    html = pb.compare_section("1", index, JUNE)
    assert '<section id="compare" aria-labelledby="compare-h">' in html
    assert '<h2 id="compare-h">Colleges to compare</h2>' in html
    text = _text(html)
    assert (
        "The 2 other public colleges in Texas that award mostly bachelor’s degrees, closest in "
        "size first. Same state, same type, nearest in size. A place to start a comparison, not "
        "a judgment of quality." in text
    )
    # It is not called similar: one row in six is more than double or under half the size.
    assert "similar" not in text.lower()
    rows = re.findall(r"<tr><td>(.*?)</td></tr>", html, re.S)
    assert len(rows) == 2
    assert '<a href="/college/near-college/">Near College</a>' in rows[0]
    assert '<td class="num">1,100</td>' in rows[0]
    # The qualifier stays beside the count in the cell, not only in the heading.
    assert '<span class="peers__n">32 of 32 assessed</span>' in rows[0]
    assert (
        '<a href="/compare/?schools=1,2" aria-label="Compare Home College with Near College">'
        in rows[0]
    )
    # No verdict is a reason, never 0 of 0.
    assert '<span class="peers__n">not assessed</span>' in rows[1]
    assert '<th class="num">Undergraduate programs above the high-school line</th>' in html
    assert "Enrollment is degree-seeking undergraduates, fall 2024." in text
    assert "<details" not in html and EM_DASH not in html


def test_the_rule_sentence_matches_how_many_colleges_it_found():
    def rule(n):
        colleges = [_peer("1", "Home College", 1000)]
        colleges += [_peer(str(10 + i), f"College {i}", 1000 + i) for i in range(n)]
        return _text(pb.compare_section("1", pb.PeerIndex(colleges), JUNE))

    assert "The one other public college in Texas that awards mostly bachelor’s degrees." in rule(1)
    assert "The 5 other public colleges in Texas that award mostly" in rule(5)
    assert (
        "The 5 closest in size to Home College among the 12 other public colleges in Texas that "
        "award mostly bachelor’s degrees." in rule(12)
    )


# --- On the page -------------------------------------------------------------------------------

META = {"name": "Example University", "state": "TX", "control": "Public", "city": "Austin"}


def _row(verdict="pass"):
    return {
        "program": "Business",
        "credential": "Bachelor's Degree",
        "earnings": 60000,
        "premium": 25000,
        "verdict": verdict,
        "horizon": "4yr_after_completion",
        "debt": 20000,
        "payback": 1.5,
        "completers": 100,
    }


def test_the_sections_sit_where_the_page_says_and_the_links_follow():
    plain, _ = canonical_page(META, [_row()], "example-university", 35000, 150)
    assert "3 sections</p>" in plain and 'id="about"' not in plain and 'id="compare"' not in plain
    about = pb.about_section(FULL, JUNE, "2026-06-10")
    index = pb.PeerIndex([_peer("1", "Example University", 1000), _peer("2", "Near College", 900)])
    compare = pb.compare_section("1", index, JUNE)
    page, _ = canonical_page(META, [_row()], "example-university", 35000, 150, None, about, compare)
    assert pl.nav_items(True, True) == [
        ("cost", "Cost"),
        ("about", "About"),
        ("programs", "Programs"),
        ("compare", "Compare"),
        ("sources", "Sources"),
    ]
    links = '<li><a href="#cost">Cost</a></li><li><a href="#about">About</a></li><li><a href="#programs">Programs</a></li><li><a href="#compare">Compare</a></li><li><a href="#sources">Sources</a></li>'
    # The same five in the side rail and in the section bar, and the bar counts them.
    assert page.count(links) == 2
    assert '<p class="sectnav__label" id="sn-l">5 sections</p>' in page
    order = [
        page.index(f'<section id="{i}"')
        for i in ("cost", "about", "programs", "compare", "sources")
    ]
    assert order == sorted(order)
    # About is the last thing beside the rail: only the two blocks' closing tags separate it from
    # Programs. Colleges to compare is the last thing before Sources.
    about_ends = page.index("</section>", page.index('<section id="about"')) + len("</section>")
    assert page[about_ends : page.index('<section id="programs"')].split() == ["</div>", "</div>"]
    compare_ends = page.index("</section>", page.index('<section id="compare"')) + len("</section>")
    assert page[compare_ends : page.index('<section id="sources"')].strip() == ""
    for sid in ("cost", "about", "programs", "compare", "sources"):
        assert page.count(f'id="{sid}"') == 1


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
    "first_gen_share DOUBLE, completion_rate DOUBLE, completion_cohort INT, "
    "completion_basis VARCHAR, predominant_degree INT"
)
PASS, FAIL, NONE = "passes_earnings_premium", "fails_earnings_premium", "insufficient_data"


def _program(uid, name, control, cip, flag, level="3"):
    pay = {PASS: 70000.0, FAIL: 20000.0, NONE: None}[flag]
    return (
        uid,
        name,
        "TX",
        control,
        cip,
        f"Field {cip}.",
        level,
        "Bachelor's Degree" if level == "3" else "Master's Degree",
        50,
        pay,
        "4yr_after_completion" if pay else None,
        35000.0,
        None if pay is None else pay - 35000.0,
        20000.0,
        None,
        None,
        flag,
    )


def test_the_live_build_puts_both_sections_on_every_profile_and_the_counts_agree(
    tmp_path, monkeypatch, register_fixture_slugs
):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({VC_COLS})")
    programs = [
        _program("100", "Alpha State University", "Public", "5201", PASS),
        _program("100", "Alpha State University", "Public", "5202", FAIL),
        _program("101", "Beta State University", "Public", "5201", PASS),
        _program("101", "Beta State University", "Public", "5202", PASS),
        # A graduate program above the line is not an undergraduate count.
        _program("101", "Beta State University", "Public", "5203", PASS, level="5"),
        _program("102", "Gamma State University", "Public", "5201", NONE),
        _program("103", "Delta College", "Private, nonprofit", "5201", PASS),
        _program("104", "Epsilon Institute", "Public", "5201", PASS),
    ]
    con.executemany(f"INSERT INTO vc VALUES ({','.join(['?'] * 17)})", programs)
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")
    con.execute(f"CREATE TABLE inst({INST_COLS})")
    np = "18000,12000,14000,20000,24000,28000"
    con.execute(
        f"""INSERT INTO inst VALUES
        ('100','Austin','www.alpha.edu/',5000,{np},0.4,0.3,0.75,1200,'four_year',3),
        ('101','Dallas','https://beta.edu',5200,{np},0.5,0.3,1.0,6,'four_year',3),
        ('102','Houston',NULL,9000,{np},NULL,NULL,NULL,NULL,NULL,3),
        ('103','Waco','delta.edu',5100,{np},0.2,0.3,0.6,400,'four_year',3)"""
    )
    con.execute(f"COPY inst TO '{pq / 'institutions.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bs, "PARQUET_DIR", pq)
    monkeypatch.setattr(bcp, "SITE", tmp_path / "site")
    register_fixture_slugs()
    bcp.main()

    def page(slug):
        return (tmp_path / "site" / "college" / slug / "index.html").read_text()

    alpha = page("alpha-state-university")
    assert '<p class="sectnav__label" id="sn-l">5 sections</p>' in alpha
    facts = _facts(alpha)
    assert facts["Undergraduates"][0] == "5,000"
    assert facts["Completion rate"][0] == "75%"
    assert (
        f"who started in {pb.years_for(SCORECARD_RELEASE).four_year}" in facts["Completion rate"][1]
    )
    # The two other public colleges, nearest in size first. The private college is not one.
    compare = alpha[alpha.index('<section id="compare"') : alpha.index('<section id="sources"')]
    names = re.findall(r'<tr><td><a href="/college/[^"]+/">(.*?)</a>', compare)
    assert names == ["Beta State University", "Gamma State University"]
    assert "Delta College" not in compare
    assert '<a href="/compare/?schools=100,101"' in compare
    # Beta's row repeats Beta's own headline: two undergraduate programs, not its graduate one.
    assert '<span class="peers__n">2 of 2 assessed</span>' in compare
    beta = page("beta-state-university")
    assert (
        '<span class="kf__num">2</span><span class="kf__of">of 2 assessed undergraduate programs'
        in beta
    )
    # Gamma has no verdict: its row says so.
    assert '<span class="peers__n">not assessed</span>' in compare
    # Beta's 100% rests on six students, and its page says so.
    assert "A small group:" in _facts(beta)["Completion rate"][1]
    # A college ED's institution file does not list still gets both sections, saying why.
    epsilon = page("epsilon-institute")
    assert "does not list this college, so none of these figures is published" in _text(epsilon)
    assert "so colleges of the same kind cannot be picked" in _text(epsilon)
    assert '<p class="sectnav__label" id="sn-l">5 sections</p>' in epsilon


# --- The data ----------------------------------------------------------------------------------


RAW_FOS = """UNITID,OPEID6,INSTNM,CONTROL,CIPCODE,CIPDESC,CREDLEV,CREDDESC,IPEDSCOUNT1,EARN_MDN_1YR,EARN_MDN_4YR,DEBT_ALL_STGP_EVAL_MDN
100,001000,Four Year University,Public,0101,Computer Science.,3,Bachelor's Degree,120,40000,60000,20000
"""
# 300 has ED's literal 0 for a college with no first-time, full-time cohort. 500 has that 0 in the
# four-year column and a real less-than-four-year rate, with a stray four-year cohort beside it.
RAW_INST = """UNITID,INSTNM,CITY,STABBR,INSTURL,UGDS,EARN_THR_STATE,EARN_THR_NAT,PCTPELL,C150_4,C150_L4,D150_4,D150_L4,PREDDEG
100,Four Year University,Testville,TX,fyu.edu,12000,35000,36000,0.4,0.6,NA,500,NA,3
200,Trade School,Testville,TX,trade.edu,300,35000,36000,0.7,NA,0.25,NA,40,1
300,Graduate Institute,Testville,TX,grad.edu,NA,35000,36000,NA,0,NA,0,NA,4
400,Unclassified College,Testville,TX,NA,50,35000,36000,NA,NA,NA,NA,NA,0
500,Mixed College,Testville,TX,mixed.edu,900,35000,36000,0.5,0,0.5,999,10,2
"""


def test_the_spine_keeps_each_rate_with_its_own_cohort_and_kind(tmp_path, monkeypatch):
    import pipeline.build_spine as spine

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "Most-Recent-Cohorts-Field-of-Study.csv").write_text(RAW_FOS)
    (raw / "Most-Recent-Cohorts-Institution.csv").write_text(RAW_INST)
    monkeypatch.setattr(spine, "DB_PATH", tmp_path / "tw.duckdb", raising=False)
    monkeypatch.setattr(spine, "PARQUET_DIR", tmp_path / "parquet", raising=False)
    monkeypatch.setattr(spine, "RAW_DIR", raw)
    spine.main()
    path = tmp_path / "parquet" / "institutions.parquet"
    got = {
        r[0]: r[1:]
        for r in duckdb.connect()
        .execute(
            f"""SELECT unitid, completion_rate, completion_cohort, completion_basis,
                       predominant_degree FROM read_parquet('{path}')"""
        )
        .fetchall()
    }
    assert got["100"] == (0.6, 500, "four_year", 3)
    assert got["200"] == (0.25, 40, "less_than_four_year", 1)
    # No rate, so no cohort and no kind: a cohort of 0 beside "not published" would read as a fact.
    assert got["300"] == (None, None, None, 4)
    assert got["400"] == (None, None, None, 0)
    # The rate that is used brings its own cohort, not the other column's.
    assert got["500"] == (0.5, 10, "less_than_four_year", 2)
    assert validate.check_completion_cohort(path)[0]


def test_the_published_institutions_file_has_a_cohort_for_every_rate():
    path = ROOT / "published" / "institutions.parquet"
    ok, detail = validate.check_completion_cohort(path)
    assert ok, detail
    con = duckdb.connect()
    cols = {
        r[0]: r[1] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
    }
    assert cols["completion_cohort"] == "INTEGER" and cols["predominant_degree"] == "INTEGER"
    degrees = {
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT predominant_degree FROM read_parquet('{path}')"
        ).fetchall()
    }
    assert degrees <= {0, 1, 2, 3, 4, None}
    # Every profile builds from this file, so it must load.
    assert pb.load(con, path)


@pytest.mark.parametrize(
    "row",
    [
        "(0.5, NULL, 'four_year')",  # a rate with no cohort
        "(0.5, 0, 'four_year')",  # a cohort of nobody
        "(NULL, 40, NULL)",  # a cohort with no rate
        "(0.5, 40, NULL)",  # no kind of rate, so no year
        "(0.5, 40, 'six_year')",  # a kind the page has no year for
        "(0.5, 3, 'four_year')",  # 1.5 students: not this rate's cohort
    ],
)
def test_the_data_gate_fails_a_rate_whose_cohort_is_missing_or_does_not_fit(tmp_path, row):
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE inst(completion_rate DOUBLE, completion_cohort INTEGER, completion_basis VARCHAR)"
    )
    con.execute("INSERT INTO inst VALUES (0.75, 1200, 'four_year'), (NULL, NULL, NULL)")
    good = tmp_path / "good.parquet"
    con.execute(f"COPY inst TO '{good}' (FORMAT PARQUET)")
    assert validate.check_completion_cohort(good)[0]
    con.execute(f"INSERT INTO inst VALUES {row}")
    bad = tmp_path / "bad.parquet"
    con.execute(f"COPY inst TO '{bad}' (FORMAT PARQUET)")
    assert not validate.check_completion_cohort(bad)[0]


def test_the_data_gate_fails_when_it_cannot_measure(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE inst(completion_rate DOUBLE)")
    con.execute("INSERT INTO inst VALUES (0.75)")
    path = tmp_path / "institutions.parquet"
    con.execute(f"COPY inst TO '{path}' (FORMAT PARQUET)")
    ok, detail = validate.check_completion_cohort(path)
    assert not ok and "completion_cohort" in detail


# --- Layout ------------------------------------------------------------------------------------


def test_the_facts_stack_by_text_size_and_a_count_never_splits():
    css = (ROOT / "site" / "profile.css").read_text()
    # Two columns to one by the block's own width in em, so enlarged text stacks the facts.
    assert ".basics { container: basics / inline-size; }" in css
    assert (
        "@container basics (max-width: 34em) { .basics__facts { grid-template-columns: minmax(0, 1fr); } }"
        in css
    )
    assert ".peers__n { white-space: nowrap; }" in css
    # On a phone card a value that does not fit beside its label drops below it.
    assert ".peers table.t.stack td { flex-wrap: wrap; }" in css
    assert ".peers table.t.stack td::before { flex: 1 1 8em; min-width: 0; }" in css
    # A long web address wraps instead of widening the page.
    assert re.search(r"\.basics__fig \{[^}]*overflow-wrap: anywhere", css)
    # The figure is modest: the section has no display-size number.
    assert "var(--t-sub)" in re.search(r"\.basics__fig \{[^}]*\}", css).group(0)
