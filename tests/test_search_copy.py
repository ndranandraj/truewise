"""Titles and search descriptions per page family (Prototype P).

What these guard, in the order a reader would be misled:
  * a description a search result cuts, which can cut off the words that qualify its number;
  * a shortened description that drops a qualifier ("assessed", "undergraduate", "graduate",
    "not the federal test for them", the credential behind a figure);
  * two pages with one description, or two same-named campuses told apart by nothing real;
  * a title that loses the words people search for, or a place that is not on record.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

import pipeline.build_majors_pages as bm
import pipeline.profile_copy as pc
from pipeline.build_college_pages import national_index, state_index
from pipeline.search_copy import DESC_MAX, agree, fit, fitting, n_of

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
EM_DASH = chr(0x2014)


# --- The rules -------------------------------------------------------------------------------------


def test_the_limit_is_what_a_search_result_shows():
    # The review's rule (13 November 2026): 155 characters, so no description is cut.
    assert DESC_MAX == 155


def test_fit_takes_the_first_wording_that_fits_and_stops_when_none_does():
    assert fit("x" * 200, "y" * DESC_MAX, "z") == "y" * DESC_MAX
    with pytest.raises(SystemExit, match="no description fits"):
        fit("x" * (DESC_MAX + 1))
    assert fitting("a" * 200, "b", "b", "c") == ["b", "c"]
    with pytest.raises(SystemExit):
        fitting("x" * 200)


def test_counts_agree_with_their_noun_and_verb():
    assert n_of(1, "program") == "1 program" and n_of(2, "program") == "2 programs"
    assert agree(1, 5, "has", "have") == "has"  # 1 of 5 programs has
    assert agree(0, 1, "has", "have") == "has"  # 0 of 1 program has
    assert agree(3, 5, "has", "have") == "have"
    assert agree(0, 5, "has", "have") == "have"


# --- Profiles --------------------------------------------------------------------------------------


def _r(verdict, grad=False, done=10, horizon="4yr_after_completion"):
    return {"verdict": verdict, "grad": grad, "completers": done, "horizon": horizon}


BAYLOR = {"name": "Baylor University", "state": "TX", "city": "Waco"}


def test_the_title_puts_what_the_page_answers_before_the_place():
    assert pc.title(BAYLOR) == "Baylor University: graduate earnings and cost, Waco, TX"
    assert pc.title({"name": "X College", "state": "TX", "city": None}) == (
        "X College: graduate earnings and cost, TX"
    )
    assert pc.title({"name": "X College", "state": "ZZ", "city": None}) == (
        "X College: graduate earnings and cost"
    )


def test_the_description_leads_with_the_summary_boxs_number():
    rows = [_r("pass")] * 49 + [_r("fail")] * 2 + [_r("insufficient")] * 10 + [_r("pass", True)]
    assert pc.description(BAYLOR, rows) == (
        "Baylor University, Waco, TX: 49 of 51 assessed undergraduate programs have graduates "
        "earning more than a typical Texas high-school graduate."
    )
    # One program: the noun and the verb agree with it, never "all 1 ... programs".
    one = pc.description({"name": "S U", "state": "CA", "city": "Oakland"}, [_r("pass")])
    assert "1 of 1 assessed undergraduate program has graduates" in one
    none_above = pc.description(BAYLOR, [_r("fail")])
    assert "0 of 1 assessed undergraduate program has graduates" in none_above


def test_each_case_says_what_the_summary_says():
    grad = pc.description(BAYLOR, [_r("pass", True)] * 11 + [_r("insufficient")])
    assert "11 of 11 assessed graduate programs have graduates" in grad
    assert "the Texas high-school line" in grad or "a typical Texas high-school graduate" in grad
    assert "not the federal test for" in grad
    nob = pc.description(BAYLOR, [_r("nobench")])
    assert nob == (
        "Baylor University, Waco, TX: ED publishes earnings for its one program, but no state "
        "high-school benchmark to compare it with."
    )
    some = pc.description(BAYLOR, [_r("nobench"), _r("nobench"), _r("insufficient")])
    assert "ED publishes earnings for 2 of its 3 programs" in some
    allnb = pc.description(BAYLOR, [_r("nobench"), _r("nobench")])
    assert "ED publishes earnings for all 2 of its programs" in allnb
    noearn = pc.description(BAYLOR, [_r("insufficient")] * 3)
    assert (
        "ED publishes no graduate earnings for any of its 3 programs, so none can be assessed."
        in noearn
    )
    nothing = pc.description(BAYLOR, [_r("none")])
    assert (
        nothing
        == "Baylor University, Waco, TX: ED lists its one program but reports no figures for it."
    )


@pytest.mark.parametrize("n", [40, 60, 75, 86, 100])
def test_a_long_name_shortens_the_wording_but_never_drops_a_qualifier(n):
    name = ("Institute of Technology and Allied Health Sciences " * 3)[:n].strip()
    meta = {"name": name, "state": "LA", "city": "Baton Rouge"}
    ug = pc.description(meta, [_r("pass")] * 11)
    assert len(ug) <= DESC_MAX
    assert "11 of 11 assessed undergraduate programs" in ug
    assert "Louisiana" in ug, "the line is the state's, at every length"
    grad = pc.description(meta, [_r("pass", True)] * 11)
    assert len(grad) <= DESC_MAX
    assert "assessed graduate programs" in grad and "not the federal test for" in grad
    assert "Louisiana" in grad
    # The place stays whenever the name has to go; a bare sentence never names nothing.
    assert grad.startswith(name) or grad.startswith("Baton Rouge, LA: ")


def test_a_name_too_long_with_no_place_on_record_stops_the_build():
    meta = {"name": "N" * 150, "state": "ZZ", "city": None}
    with pytest.raises(SystemExit, match="no description fits"):
        pc.description(meta, [_r("pass")])


def _pages(entries):
    return {u: (pc.options(m, rows), pc.separating(m, rows)) for u, m, rows in entries}


def test_same_named_campuses_are_told_apart_by_a_real_fact_and_both_say_it():
    meta = {"name": "Cortiva Institute", "state": "FL", "city": "Maitland"}
    a = [_r("fail", done=40), _r("fail", done=48)]
    b = [_r("fail", done=80), _r("fail", done=78)]
    got = pc.choose(_pages([("2", meta, b), ("1", meta, a)]))
    assert got["1"].endswith(" 88 recent graduates.") and got["2"].endswith(
        " 158 recent graduates."
    )
    assert "Maitland, FL" in got["1"] and "Maitland, FL" in got["2"], "the city is never traded"
    # Where the first wording had to drop the city, the city is the fact that separates them.
    long = "Lawrence & Company College of Cosmetology and Barbering Arts"
    x = {"name": long, "state": "CA", "city": "Hanford"}
    y = {"name": long, "state": "CA", "city": "Selma"}
    rows = [_r("fail")]
    first_x = pc.options(x, rows)[0]
    if "Hanford" not in first_x:
        got = pc.choose(_pages([("1", x, rows), ("2", y, rows)]))
        assert "Hanford, CA" in got["1"] and "Selma, CA" in got["2"]


def test_campuses_whose_facts_are_the_same_never_get_a_wording_that_merely_differs():
    meta = {"name": "Trend Barber College", "state": "TX", "city": "Houston"}
    rows = [_r("fail", done=15)]
    got = pc.choose(_pages([("9", meta, rows), ("1", meta, list(rows))]))
    assert got["9"] == got["1"] == pc.options(meta, rows)[0]
    # And the order pages arrive in changes nothing.
    other = [("9", meta, [_r("fail", done=15)]), ("1", meta, [_r("fail", done=43)])]
    assert pc.choose(_pages(other)) == pc.choose(_pages(other[::-1]))


def test_pages_that_share_every_fact_keep_one_description_rather_than_invent_one():
    meta = {"name": "Royal Learning Institute", "state": "ZZ", "city": None}
    rows = [{"verdict": "none", "grad": False, "completers": None}]
    got = pc.choose(_pages([("1", meta, rows), ("2", meta, rows)]))
    assert (
        got["1"]
        == got["2"]
        == "Royal Learning Institute: ED lists its one program but reports no figures for it."
    )


def test_the_profile_page_carries_the_title_and_the_description():
    from pipeline.build_canonical_profiles import canonical_page

    row = {
        "program": "Business",
        "credential": "Bachelor's Degree",
        "earnings": 60000,
        "premium": 25000,
        "verdict": "pass",
        "horizon": "4yr_after_completion",
        "debt": 20000,
        "payback": 1.5,
        "completers": 100,
    }
    meta = {**BAYLOR, "control": "Private, nonprofit"}
    page, _ = canonical_page(meta, [row], "baylor-university", 35000, 150)
    assert "<title>Baylor University: graduate earnings and cost, Waco, TX</title>" in page
    desc = html.unescape(re.search(r'name="description" content="(.*?)"', page).group(1))
    assert desc == pc.description(meta, [row])
    og = html.unescape(re.search(r'property="og:description" content="(.*?)"', page).group(1))
    assert og == desc
    chosen, _ = canonical_page(
        meta, [row], "baylor-university", 35000, 150, description="A chosen description."
    )
    assert 'name="description" content="A chosen description."' in chosen


def test_the_live_build_passes_each_profile_its_chosen_description():
    src = (ROOT / "pipeline" / "build_college_pages.py").read_text()
    assert "profile_copy.choose(" in src and "description=descriptions[u]" in src


# --- Majors ----------------------------------------------------------------------------------------


def _cred(short, med, credential):
    return {
        "credential": credential,
        "cred_short": short,
        "med": med,
        "programs": 10,
        "schools": 10,
        "p25": None,
        "p75": None,
        "pass_pct": None,
        "cip": "1204",
        "cip2": "12",
        "cred": "1",
        "demand": None,
        "family": "Personal and Culinary Services",
        "name": "Cosmetology and Related Personal Grooming Services.",
    }


def test_every_credential_label_reads_after_its_article():
    for short, (phrase, word) in bm.CRED_PHRASE.items():
        assert phrase.split()[0] == ("an" if phrase.split()[1][0] in "aeiou" else "a"), short
        assert word and " " not in word
    with pytest.raises(SystemExit, match="no wording for the credential"):
        bm.cred_phrase("Something new")


def test_the_major_title_says_whose_figure_before_the_figure(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "SITE", tmp_path / "site")
    creds = [_cred("Undergrad cert", 25483.0, "Undergraduate Certificate or Diploma")]
    page = bm.major_page("1204", creds[0]["name"], creds[0]["family"], creds, "cosmetology")
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    assert title == "Cosmetology: certificate graduates earned a median $25,483"
    desc = html.unescape(re.search(r'name="description" content="(.*?)"', page).group(1))
    assert desc.startswith(
        "Cosmetology graduates with an undergraduate certificate earned $25,483 at the median US "
        "program, a few years after finishing."
    )
    assert len(desc) <= DESC_MAX
    # The page's own sentence: never "with a undergrad cert".
    assert "graduates with an undergraduate certificate typically" in page
    assert "with a undergrad" not in page and "with a associate" not in page


def test_a_long_field_name_keeps_the_credential_in_the_description():
    field = "Electrical/Electronics Maintenance and Repair Technologies/Technicians"
    d = bm.major_description(field, "Undergrad cert", "$43,812")
    assert len(d) <= DESC_MAX and "certificate" in d and "$43,812" in d
    assert "a few years after finishing" in d


# --- State and national college pages --------------------------------------------------------------


def _school(n_fail=0):
    return ("x", {"n_fail": n_fail, "n_pass": 0, "name": "X", "n_dec": 0, "net_price": None}, "1")


def test_state_pages_count_colleges_in_the_singular_and_fit():
    one = state_index("MP", [_school()])
    desc = html.unescape(re.search(r'name="description" content="(.*?)"', one).group(1))
    assert desc.startswith("1 college in Northern Mariana Islands:") and len(desc) <= DESC_MAX
    assert "<title>Colleges in Northern Mariana Islands: graduate earnings and cost</title>" in one
    nat = national_index(["TX"], profiled=1, searchable=1)
    nd = html.unescape(re.search(r'name="description" content="(.*?)"', nat).group(1))
    assert len(nd) <= DESC_MAX


# --- Every page on the site ------------------------------------------------------------------------


def test_no_indexed_page_has_a_description_a_search_result_cuts():
    """The committed pages always; every generated page too after a build (the deploy job builds
    the whole site before it runs pytest)."""
    desc = re.compile(r'<meta name="description" content="(.*?)"', re.S)
    bad, seen = [], 0
    for path in sorted(SITE.rglob("*.html")):
        rel = path.relative_to(SITE).as_posix()
        if rel.startswith(("_proto/", "_measure/", "components/")):
            continue
        page = path.read_text(encoding="utf-8", errors="replace")
        if 'name="robots" content="noindex' in page:
            continue
        m = desc.search(page)
        if not m:
            continue
        seen += 1
        text = html.unescape(m.group(1))
        if len(text) > DESC_MAX:
            bad.append(f"{rel}: {len(text)}")
        if EM_DASH in text:
            bad.append(f"{rel}: em-dash")
    assert seen >= 10, "the scan must find the committed pages, or it measures nothing"
    assert not bad, "descriptions a search result would cut:\n" + "\n".join(bad[:40])
