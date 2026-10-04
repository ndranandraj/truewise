"""The High Schools hub, action first (Prototype H, approved October 2026). Its figures are typed into
the page, so they are recomputed here from the published dataset, with the filter the site build uses
(pipeline/build_k12.py: a name and at least one enrolled student)."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
HUB = (ROOT / "site" / "k12" / "index.html").read_text()
LOOKUP = (ROOT / "site" / "k12" / "advanced-courses" / "index.html").read_text()
PARQUET = ROOT / "published" / "k12.parquet"
SEARCHABLE = f"FROM read_parquet('{PARQUET}') WHERE name IS NOT NULL AND enroll_total > 0"


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_hub_figures_match_the_published_data():
    total, none3 = duckdb.sql(
        "SELECT count(*), count(*) FILTER (WHERE offers_ap = false AND offers_calc = false "
        f"AND offers_physics = false) {SEARCHABLE}"
    ).fetchone()
    text = _text(HUB)
    assert f"any of {total:,} US public high schools" in text
    assert f"About 1 in 4 public high schools ({none3:,} of {total:,})" in text
    assert round(total / none3) == 4


def test_the_note_says_no_ap_students_and_keeps_its_qualifier():
    note = _text(HUB.split('<aside class="k-fact"', 1)[1].split("</aside>", 1)[0])
    assert "reported no AP students and no calculus or physics classes" in note
    assert (
        "a count that includes alternative, special-education and juvenile-justice schools" in note
    )
    # "No AP students" stays distinct from "no AP courses" (review of Prototype H): the note keeps its
    # wording and is never simplified into a claim that schools offer no advanced courses.
    assert "no AP courses" not in note and "offer no advanced courses" not in note


def test_search_comes_first_and_hands_off_to_the_lookup():
    hero = HUB.split('<section class="k-hero">', 1)[1].split("</section>", 1)[0]
    assert "<h1>What does your high school offer?</h1>" in hero
    assert hero.index("<h1>") < hero.index('class="lede"') < hero.index('class="k-search"')
    assert hero.index('class="k-search"') < hero.index('class="k-fact"')
    assert (
        '<form class="k-search" action="/k12/advanced-courses/" method="get" role="search">' in hero
    )
    assert 'name="q"' in hero and '<label for="k-q">Find a high school</label>' in hero
    # The shared control and button, not one-off styles (test_ui_regressions checks every page).
    assert (
        'id="k-q" class="control"' in hero
        and '<button type="submit" class="btn">Search</button>' in hero
    )
    # The lookup reads ?q= into its search box.
    assert 'return renderSearch(params.q || "");' in LOOKUP
    # The search replaced the Courses & staff tile; the other two tools stay.
    tiles = HUB.split('<div class="live-modules">', 1)[1].split("</div>", 1)[0]
    assert 'href="/k12/advanced-courses/"' not in tiles
    assert 'href="/k12/rankings/"' in tiles and 'href="/k12/compare/"' in tiles


def test_examples_are_labelled_links_to_schools_that_exist():
    hero = HUB.split('<section class="k-hero">', 1)[1].split("</section>", 1)[0]
    assert '<p class="k-hint" id="k-ex-h">Examples, not recommendations</p>' in hero
    keys = re.findall(r'<li><a href="/k12/advanced-courses/\?school=(\d+)">', hero)
    assert len(keys) == 5
    found = {
        r[0]
        for r in duckdb.sql(
            f"SELECT combokey {SEARCHABLE} AND combokey IN ({','.join(repr(k) for k in keys)})"
        ).fetchall()
    }
    assert found == set(keys), f"example schools missing from the data: {set(keys) - found}"


def test_descriptions_promise_only_what_the_section_has():
    head = HUB.split("</head>", 1)[0]
    assert "unclaimed" not in head and "financial aid" not in head


def test_lookup_intro_is_one_sentence_and_enrollment_is_never_n_a():
    lede = re.search(r'<p class="lede">(.*?)</p>', LOOKUP, re.S).group(1)
    assert lede.count(". ") == 0 and lede.rstrip().endswith(".")
    assert "${num(s.enroll)} students</div>" not in LOOKUP
    assert 's.enroll == null ? "enrollment not reported"' in LOOKUP


def test_school_names_may_hyphenate_and_the_layout_check_measures_a_school_page():
    """CRDC names are in capitals; at 200% text one word was wider than a 320px phone."""
    css = re.sub(
        r"/\*.*?\*/", "", LOOKUP.split("<style>", 1)[1].split("</style>", 1)[0], flags=re.S
    )
    assert ".sch-head h1, .k-head h1 { overflow-wrap: break-word; hyphens: auto; }" in css
    assert ".sch-head { container: sch-head / inline-size; }" in css
    assert (
        "@container sch-head (max-width: 12em) { .sch-head h1 { font-size: var(--t-lede); } }"
        in css
    )
    assert '<html lang="en">' in LOOKUP
    probe = (ROOT / "tests" / "layout_probe.js").read_text()
    assert 'label: "k12-school", path: "/k12/advanced-courses/?school=362058002877"' in probe
