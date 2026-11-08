"""A school that leaves ED's data keeps an address that says so."""

from __future__ import annotations

import re
from pathlib import Path

from pipeline import retired_schools as rs

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = {"1": "stays", "2": "leaves", "3": "left-before", "4": "returns", "5": "never-a-page"}
OLD = {"1": ("Stays", "TX"), "2": ("Leaves", "CT"), "5": ("No page", "OH")}
NEW = {"1": ("Stays", "TX"), "4": ("Returns", "NY")}
EARLIER = [
    {
        "unitid": "3",
        "slug": "left-before",
        "name": "Left",
        "state": None,
        "last_release": "2026-01-01",
    },
    {
        "unitid": "4",
        "slug": "returns",
        "name": "Returns",
        "state": "NY",
        "last_release": "2026-01-01",
    },
]


def test_records_who_left_and_keeps_who_left_before():
    registry = {k: v for k, v in REGISTRY.items() if k != "5"}
    got = rs.updated_record(OLD, NEW, registry, EARLIER, "2026-06-10")
    assert [e["slug"] for e in got] == ["leaves", "left-before"]
    leaves = got[0]
    assert (leaves["name"], leaves["state"], leaves["last_release"]) == (
        "Leaves",
        "CT",
        "2026-06-10",
    )
    # An earlier departure keeps the release it was last in.
    assert got[1]["last_release"] == "2026-01-01"


def test_a_school_that_returns_leaves_the_record():
    got = rs.updated_record(OLD, NEW, REGISTRY, EARLIER, "2026-06-10")
    assert "returns" not in {e["slug"] for e in got}


def test_a_school_with_no_registered_page_is_not_recorded():
    got = rs.updated_record(OLD, NEW, {"1": "stays"}, [], "2026-06-10")
    assert got == []


def test_both_spellings_of_an_address_redirect_and_the_block_is_rewritten_in_place():
    record = [{"slug": "leaves"}]
    first = rs.with_rules("/college /colleges/ 301\n", record)
    assert "/college/leaves/ /colleges/no-longer-listed/#leaves 301" in first
    assert "/college/leaves /colleges/no-longer-listed/#leaves 301" in first
    assert first.startswith("/college /colleges/ 301\n")
    second = rs.with_rules(first + "/after /x 301\n", [{"slug": "other"}])
    assert "leaves" not in second and "/college/other/ " in second
    assert second.startswith("/college /colleges/ 301\n") and second.endswith("/after /x 301\n")


def test_every_retired_school_is_redirected_and_no_live_school_is():
    """The committed record and _redirects agree, and a redirect never shadows a real page: rules
    run before assets, so one left behind would hide a school that came back."""
    record = rs.load()
    assert record, "the November 2026 release retired 156 schools"
    rules = (ROOT / "site" / "_redirects").read_text()
    slugs = {e["slug"] for e in record}
    assert (
        set(re.findall(r"^/college/([^/\s]+)/ /colleges/no-longer-listed/#", rules, re.M)) == slugs
    )
    assert len(rules.splitlines()) < 2000, "Cloudflare allows 2,000 static redirects"
    map_path = ROOT / "site" / "college" / "slug-map.json"
    if map_path.exists():
        import json

        assert not slugs & set(json.loads(map_path.read_text()).values())


def test_the_page_names_each_school_at_its_anchor():
    from pipeline.build_college_pages import retired_page

    html = retired_page(
        [
            {"slug": "a-school", "name": "A & School", "state": "CT", "last_release": "2026-06-10"},
            {"slug": "b-school", "name": "B School", "state": None, "last_release": "2026-06-10"},
        ]
    )
    assert '<li id="a-school">' in html and "A &amp; School" in html
    assert "Connecticut" in html and "Location not reported" in html
    assert 'rel="canonical" href="https://truewise.dev/colleges/no-longer-listed/"' in html
    # It says what the absence means and does not assert a closure it cannot show.
    assert "often a sign" in html and "—" not in html
