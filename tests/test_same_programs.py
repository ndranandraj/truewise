"""The same programs at other colleges in the state, on no-verdict profiles (Prototype O).

What these guard, in the order a reader would be misled:
  * another college's graduates read as this college's (the labels in heading, lede and column);
  * a sentence that says no other college in the state publishes earnings when one does;
  * a program counted twice because two campuses share ED's figures, or a campus of this college
    counted as another college, or a branch campus in the state left out;
  * the section on a profile whose own earnings are published, where its first sentence is false;
  * an order, a cap or a "more" sentence that changes between builds or miscounts.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import duckdb
import pytest

import pipeline.build_college_pages as bcp
import pipeline.build_site as bs
import pipeline.profile_layout as pl
import pipeline.same_programs as sp
from pipeline.build_canonical_profiles import canonical_page

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)
PASS, FAIL, NONE = "passes_earnings_premium", "fails_earnings_premium", "insufficient_data"
NM, TX = 32204.0, 35000.0

VC_COLS = (
    "unitid VARCHAR, inst_name VARCHAR, state VARCHAR, control VARCHAR, cip_code VARCHAR, "
    "cip_desc VARCHAR, credential_level VARCHAR, credential_desc VARCHAR, completers_count INT, "
    "earnings DOUBLE, earnings_horizon VARCHAR, earnings_threshold_state DOUBLE, "
    "earnings_premium_state DOUBLE, debt_median DOUBLE, debt_to_earnings_ratio DOUBLE, "
    "debt_payback_years DOUBLE, value_flag VARCHAR, opeid6 VARCHAR"
)
DESC = {
    "1204": "Cosmetology and Related Personal Grooming Services.",
    "5108": "Allied Health and Medical Assisting Services.",
    "4601": "Mason/Masonry.",
    "5201": "Business/Commerce, General.",
}
CRED_DESC = {
    "1": "Undergraduate Certificate or Diploma",
    "2": "Associate's Degree",
    "5": "Master's Degree",
}


def _vc(uid, name, state, opeid, cip, level, flag, earn=None, *, line=NM, one_year=False, done=20):
    line = None if state is None else line
    return (
        uid,
        name,
        state,
        "Private, for-profit",
        cip,
        DESC[cip],
        level,
        CRED_DESC[level],
        done,
        earn,
        None if earn is None else ("1yr_after_completion" if one_year else "4yr_after_completion"),
        line,
        None if earn is None or line is None or flag == NONE else earn - line,
        None,
        None,
        None,
        flag,
        opeid,
    )


def _rows():
    return [
        # The college the section serves: no earnings published for any program.
        _vc("900", "Served Beauty School", "NM", "000900", "1204", "1", NONE, done=39),
        _vc("900", "Served Beauty School", "NM", "000900", "5108", "1", NONE, done=12),
        _vc("900", "Served Beauty School", "NM", "000900", "4601", "1", NONE, done=5),
        # Two campuses under one federal ID, one set of figures: one program.
        _vc("901", "Chain Beauty Albuquerque", "NM", "000901", "1204", "1", FAIL, 25000.0),
        _vc("902", "Chain Beauty Santa Fe", "NM", "000901", "1204", "1", FAIL, 25000.0),
        _vc("903", "Desert Beauty", "NM", "000903", "1204", "1", PASS, 40000.0),
        _vc("903", "Desert Beauty", "NM", "000903", "5108", "1", PASS, 45000.0, one_year=True),
        # The same field at another credential is not the same program.
        _vc("903", "Desert Beauty", "NM", "000903", "1204", "2", PASS, 52000.0),
        # A campus under the served college's own ID is not another college.
        _vc("904", "Served Beauty School West", "NM", "000900", "1204", "1", PASS, 50000.0),
        # A branch in New Mexico of a group whose main campus is in Texas is in New Mexico here.
        _vc("905", "Big Chain Las Cruces", "NM", "000906", "1204", "1", PASS, 41000.0),
        _vc("906", "Big Chain", "TX", "000906", "1204", "1", PASS, 41000.0, line=TX),
        _vc("907", "Texas Beauty", "TX", "000907", "1204", "1", FAIL, 20000.0, line=TX),
        # Earnings published with no state line: the college is not served, and not counted.
        _vc("908", "Unlisted Beauty", "NM", "000908", "1204", "1", NONE, 30000.0, line=None),
        _vc("909", "Graduate Institute", "NM", "000909", "5201", "5", PASS, 70000.0),
        _vc("910", "Nowhere College", None, "000910", "1204", "1", NONE),
        # A graduate verdict does not stop the section for the undergraduate programs.
        _vc("911", "Served Graduate College", "NM", "000911", "1204", "1", NONE),
        _vc("911", "Served Graduate College", "NM", "000911", "5201", "5", PASS, 70000.0),
    ]


def _parquet(tmp_path, rows) -> Path:
    path = tmp_path / "value_check.parquet"
    con = duckdb.connect()
    con.execute(f"CREATE TABLE vc({VC_COLS})")
    con.executemany(f"INSERT INTO vc VALUES ({','.join(['?'] * 18)})", rows)
    con.execute(f"COPY vc TO '{path}' (FORMAT PARQUET)")
    return path


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


# --- Who is served, and how each program is counted ----------------------------------------------


def test_only_colleges_with_no_undergraduate_earnings_and_a_state_are_served(tmp_path):
    got = sp.load(duckdb.connect(), _parquet(tmp_path, _rows()))
    # 904 and 908 publish earnings of their own; 909 has no undergraduate program; 910 no state.
    assert sorted(got) == ["900", "911"]
    assert got["900"].state == "NM" and got["900"].line == NM


def test_each_program_is_counted_once_at_other_colleges_in_the_state(tmp_path):
    ctx = sp.load(duckdb.connect(), _parquet(tmp_path, _rows()))["900"]
    by_cip = {p.cip: p for p in ctx.programs}
    cosmo = by_cip["1204"]
    # Chain Beauty's two campuses once, Desert Beauty, and Big Chain's New Mexico branch. Not the
    # served college's own campus, not Texas, not the college without a line.
    assert (cosmo.others, cosmo.above) == (3, 2)
    assert cosmo.median == 40000.0  # the middle of 25,000, 40,000 and 41,000
    assert cosmo.name == "Cosmetology"  # as the program table names it
    assert (by_cip["5108"].others, by_cip["5108"].above, by_cip["5108"].one_year) == (1, 1, 1)
    assert by_cip["4601"].others == 0
    assert [p.cip for p in ctx.programs] == ["1204", "5108", "4601"]


def test_earnings_with_no_state_line_are_not_a_comparison_and_the_page_says_compared(tmp_path):
    # A college ED's institution file does not list publishes earnings with no line (317 such rows
    # sit beside programs this section names in the November 2026 release).
    rows = _rows() + [
        _vc("912", "Unlisted Builders", "NM", "000912", "4601", "1", NONE, 30000.0, line=None)
    ]
    ctx = sp.load(duckdb.connect(), _parquet(tmp_path, rows))["900"]
    assert {p.cip: p.others for p in ctx.programs}["4601"] == 0
    html = sp.section(ctx)
    assert (
        "No other college in New Mexico has published earnings that can be compared with the "
        "high-school line for this college&rsquo;s other program: Mason/Masonry (certificate)."
        in html
    )


def test_a_campus_under_this_colleges_id_with_a_verdict_it_lacks_stops_the_build(tmp_path):
    rows = _rows() + [
        _vc("913", "Served Beauty School East", "NM", "000900", "4601", "1", PASS, 40000.0)
    ]
    with pytest.raises(SystemExit, match="check the shared figures"):
        sp.load(duckdb.connect(), _parquet(tmp_path, rows))


def test_campuses_under_one_id_with_different_figures_stop_the_build(tmp_path):
    rows = [r for r in _rows() if r[0] != "902"]
    rows.append(_vc("902", "Chain Beauty Santa Fe", "NM", "000901", "1204", "1", FAIL, 26000.0))
    with pytest.raises(SystemExit, match="cannot be counted once"):
        sp.load(duckdb.connect(), _parquet(tmp_path, rows))


def test_a_file_without_federal_ids_counts_each_campus_as_its_own_college(tmp_path):
    rows = [r[:-1] + (None,) for r in _rows() if r[0] != "904"]
    ctx = sp.load(duckdb.connect(), _parquet(tmp_path, rows))["900"]
    assert {p.cip: p.others for p in ctx.programs}["1204"] == 4  # 901 and 902 now count apart


def _p(name, others, above=0, done=None, cip="5101", cred="1", median=40000.0, one=0):
    return sp.Program(name, cip, cred, others, above, median if others else None, one, done)


def test_the_order_is_most_comparisons_then_larger_programs_then_name():
    progs = [
        _p("Zoology", 4, done=10),
        _p("Art", 4, done=10),
        _p("Biology", 4, done=50),
        _p("Chemistry", 9),
        _p("Drama", 0, done=100),
    ]
    want = ["Chemistry", "Biology", "Art", "Zoology", "Drama"]
    assert [p.name for p in sorted(progs, key=sp.order_key)] == want
    assert [p.name for p in sorted([progs[i] for i in (4, 2, 0, 3, 1)], key=sp.order_key)] == want


# --- What the section says ------------------------------------------------------------------------


def _ctx(*progs, line=NM, state="NM"):
    return sp.Context(state, line, tuple(sorted(progs, key=sp.order_key)))


def test_the_section_says_whose_graduates_these_are_before_any_figure():
    html = sp.section(_ctx(_p("Cosmetology", 5, cip="1204", median=28153.0), _p("Masonry", 0)))
    text = _text(html)
    assert '<h2 id="elsewhere-h">The same programs at other colleges in New Mexico</h2>' in html
    # The lede comes before the table, and opens with whose earnings are missing.
    assert html.index('class="same__lede"') < html.index("<table")
    assert (
        '<p class="same__lede">ED publishes no earnings for this college&rsquo;s undergraduate '
        "programs. It does for the same programs at other colleges in New Mexico." in html
    )
    assert "<b>These are other colleges&rsquo; graduates, not this college&rsquo;s.</b>" in html
    assert "not what this college&rsquo;s graduates earn" in html
    assert (
        '<th class="num">At other colleges: above the high-school line ($32,204 a year)</th>'
        in html
    )
    assert '<th class="num">Their median earnings</th>' in html
    # Counts, never a percentage: "0 of 5" shows how thin it is.
    assert '<span class="same__n">0 of 5</span>' in html and "%" not in text
    assert "$28,153" in html
    assert EM_DASH not in html


def test_programs_with_no_comparison_are_named_and_the_count_agrees():
    one = sp.section(_ctx(_p("Cosmetology", 5), _p("Masonry", 0)))
    assert (
        "No other college in New Mexico has published earnings that can be compared with the "
        "high-school line for this college&rsquo;s other program: Masonry (certificate)." in one
    )
    many = sp.section(_ctx(_p("Cosmetology", 5), *(_p(f"Field {i}", 0) for i in range(8))))
    assert "for 8 of this college&rsquo;s programs: Field 0 (certificate)," in many
    assert "Field 5 (certificate) and 2 more." in many and "Field 6" not in many


def test_at_most_ten_are_shown_and_the_rest_are_counted_without_claiming_fewer():
    progs = [_p(f"Field {i:02d}", 20 - i) for i in range(13)]
    html = sp.section(_ctx(*progs))
    assert html.count("<tr><td>") == sp.MAX_ROWS
    assert "Field 09" in html and "Field 10" not in html
    assert (
        "The 10 with the most comparisons are shown; 3 more of this college&rsquo;s programs have "
        "at least one." in html
    )
    # A tie across the cut leaves programs out with as many comparisons as one shown: "fewer"
    # would be false, so the sentence never says it.
    assert "fewer" not in html
    assert "more of this" not in sp.section(_ctx(*progs[:10]))


def test_the_tipped_jobs_note_follows_a_cosmetology_row_that_is_shown():
    shown = sp.section(_ctx(_p("Cosmetology", 5, cip="1204")))
    assert 'Cosmetology <span class="same__tip">(tipped jobs)</span>' in shown
    assert 'out of its first rounds. <a href="/earnings-test/">What the test is</a>.' in shown
    other = sp.section(_ctx(_p("Masonry", 5)))
    assert "tipped" not in other and "/earnings-test/" not in other
    # Past the cap the row is not shown, so neither is its note.
    capped = [_p(f"Field {i:02d}", 30 - i) for i in range(10)] + [_p("Cosmetology", 1, cip="1204")]
    assert "tipped" not in sp.section(_ctx(*capped))


def test_the_notes_say_how_programs_are_counted_and_which_horizon():
    four = _text(sp.section(_ctx(_p("Masonry", 3))))
    assert (
        "campuses that share one federal institution ID share ED&rsquo;s figures and count as one"
        in four
    )
    assert "Each is judged against the New Mexico line, as on its own profile." in four
    assert "measured up to four years after finishing." in four and "one-year" not in four
    mixed = _text(sp.section(_ctx(_p("Masonry", 3, one=1), _p("Welding", 2))))
    assert (
        "with the one-year figure where the four-year one is not published (1 of these 5)." in mixed
    )


def test_with_nothing_in_the_state_the_section_says_so_and_points_to_the_table(monkeypatch):
    monkeypatch.setattr(sp, "major_slug_for", lambda cip: "masonry" if cip == "4601" else None)
    html = sp.section(_ctx(_p("Masonry", 0, cip="4601")))
    assert "<table" not in html
    assert (
        "ED publishes no earnings for this college&rsquo;s undergraduate programs, and no other "
        "college in New Mexico" in html
    )
    assert (
        "and no other college in New Mexico has published earnings for the same programs that can "
        "be compared with the high-school line, so there is nothing in the state to set beside "
        "them." in html
    )
    assert '<a href="#programs">Program earnings</a> links to it.' in html
    monkeypatch.setattr(sp, "major_slug_for", lambda cip: None)
    assert "links to it" not in sp.section(_ctx(_p("Masonry", 0, cip="4601")))


def test_a_state_without_a_line_prints_no_amount():
    html = sp.section(_ctx(_p("Masonry", 3), line=None))
    assert '<th class="num">At other colleges: above the high-school line</th>' in html


# --- On the page -----------------------------------------------------------------------------------

META = {"name": "Served Beauty School", "state": "NM", "control": "Private, for-profit"}


def _row():
    return {
        "program": "Cosmetology",
        "credential": "Undergraduate Certificate or Diploma",
        "earnings": None,
        "premium": None,
        "verdict": "insufficient",
        "horizon": None,
        "debt": None,
        "payback": None,
        "completers": 39,
    }


def test_the_section_comes_first_and_the_links_count_it():
    plain, _ = canonical_page(META, [_row()], "served-beauty-school", NM, 150)
    assert 'id="elsewhere"' not in plain and "3 sections</p>" in plain
    section = sp.section(_ctx(_p("Cosmetology", 5, cip="1204")))
    page, _ = canonical_page(META, [_row()], "served-beauty-school", NM, 150, None, "", "", section)
    assert pl.nav_items(True, True, True)[0] == ("elsewhere", "Same programs")
    links = (
        '<li><a href="#elsewhere">Same programs</a></li><li><a href="#cost">Cost</a></li>'
        '<li><a href="#programs">Programs</a></li><li><a href="#sources">Sources</a></li>'
    )
    assert page.count(links) == 2  # the rail and the section bar
    assert '<p class="sectnav__label" id="sn-l">4 sections</p>' in page
    # Straight after the section links, before Cost.
    after_nav = page.index("</nav>", page.index('class="sectnav"')) + len("</nav>")
    assert page[after_nav : page.index('<section id="elsewhere"')].strip() == ""
    assert page.index('<section id="elsewhere"') < page.index('<section id="cost"')
    assert page.count('id="elsewhere"') == 1 and page.count('id="elsewhere-h"') == 1


INST_COLS = (
    "unitid VARCHAR, city VARCHAR, school_url VARCHAR, enrollment INT, net_price_avg DOUBLE, "
    "net_price_0_30k DOUBLE, net_price_30_48k DOUBLE, net_price_48_75k DOUBLE, "
    "net_price_75_110k DOUBLE, net_price_110k_plus DOUBLE, pell_share DOUBLE, "
    "first_gen_share DOUBLE, completion_rate DOUBLE, completion_cohort INT, "
    "completion_basis VARCHAR, predominant_degree INT"
)


def _live(tmp_path, monkeypatch, register_fixture_slugs):
    pq = tmp_path / "parquet"
    pq.mkdir()
    _parquet(pq, _rows())
    con = duckdb.connect()
    con.execute(f"CREATE TABLE inst({INST_COLS})")
    np = "18000,12000,14000,20000,24000,28000"
    con.executemany(
        f"INSERT INTO inst VALUES (?, 'Albuquerque', NULL, 300, {np}, 0.7, 0.3, 0.6, 50, "
        "'less_than_four_year', 1)",
        [(u,) for u in ("900", "901", "902", "903", "904", "905", "908", "911")],
    )
    con.execute(f"COPY inst TO '{pq / 'institutions.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bs, "PARQUET_DIR", pq)
    monkeypatch.setattr(bcp, "SITE", tmp_path / "site")
    register_fixture_slugs()


def test_the_live_build_serves_exactly_the_no_verdict_profiles(
    tmp_path, monkeypatch, register_fixture_slugs
):
    _live(tmp_path, monkeypatch, register_fixture_slugs)
    bcp.main()
    college = tmp_path / "site" / "college"
    with_section = sorted(
        d.name
        for d in college.iterdir()
        if d.is_dir() and 'id="elsewhere"' in (d / "index.html").read_text()
    )
    assert with_section == ["served-beauty-school", "served-graduate-college"]
    served = (college / "served-beauty-school" / "index.html").read_text()
    assert '<p class="sectnav__label" id="sn-l">6 sections</p>' in served
    assert '<span class="same__n">2 of 3</span>' in served
    desert = (college / "desert-beauty" / "index.html").read_text()
    assert '<p class="sectnav__label" id="sn-l">5 sections</p>' in desert


def test_the_build_stops_if_the_section_and_the_summary_disagree(
    tmp_path, monkeypatch, register_fixture_slugs
):
    _live(tmp_path, monkeypatch, register_fixture_slugs)
    real = sp.load

    def load_with_a_verdict(con, path):
        got = real(con, path)
        got["903"] = got["900"]._replace(state="NM")  # Desert Beauty has verdicts of its own
        return got

    monkeypatch.setattr(sp, "load", load_with_a_verdict)
    with pytest.raises(SystemExit, match="disagrees with its profile"):
        bcp.main()


# --- The June 2026 release --------------------------------------------------------------------------

JUNE_VC = "bb6e95ca619b625b773afbb9cf7a24284012fbeb8706652349071479fb0bf018"
VC_PATH = ROOT / "published" / "value_check.parquet"


@pytest.mark.skipif(
    not VC_PATH.exists() or hashlib.sha256(VC_PATH.read_bytes()).hexdigest() != JUNE_VC,
    reason="pinned to the 2026-06-10 value_check file",
)
def test_the_june_release_serves_645_profiles_and_the_review_example():
    con = duckdb.connect()
    got = sp.load(con, VC_PATH)
    assert len(got) == 645
    assert sum(1 for c in got.values() if any(p.others for p in c.programs)) == 596
    # The review's example: A Better U Beauty Barber Academy, Albuquerque.
    abu = got["493868"]
    assert (abu.state, abu.line) == ("NM", 32204.0)
    assert [(p.name, p.cred, p.others, p.above, round(p.median)) for p in abu.programs] == [
        ("Cosmetology", "1", 5, 0, 28153)
    ]
    # Independently of the loader: no served college has undergraduate earnings or a state gap.
    served = ",".join(f"'{u}'" for u in got)
    bad = con.execute(
        f"""SELECT count(*) FROM read_parquet('{VC_PATH}') WHERE unitid IN ({served})
            AND (state IS NULL OR (coalesce(credential_level, '') NOT IN ('4','5','6','7','8')
                 AND (earnings IS NOT NULL OR value_flag != 'insufficient_data')))"""
    ).fetchone()[0]
    assert bad == 0


def test_profile_css_keeps_counts_whole_and_lets_a_value_drop_below_its_label():
    css = (ROOT / "site" / "profile.css").read_text()
    assert ".same__n { white-space: nowrap; }" in css
    assert ".same table.t.stack td { flex-wrap: wrap; }" in css
    assert ".same table.t.stack td::before { flex: 1 1 8em; min-width: 0; }" in css
    assert ".same table.t.stack td > .same__n { margin-left: auto; }" in css
