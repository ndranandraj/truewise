"""Findings and Majors in the header (Prototype R, approved 22 November 2026).

What these guard:
  * the header's links: Majors and Findings, in place of Careers and Data (a homepage anchor);
  * Majors opening /majors/, the index of every major (Anand's choice), not /careers/;
  * each section page marking its own link, and a renamed link never dropping a mark silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pipeline.build_college_pages as bcp

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def _nav(html: str) -> list[tuple[str, str, str | None]]:
    """[(href, label, aria-current)] for the header bar's links, before the menu."""
    nav = re.search(r'<nav aria-label="Primary">(.*?)<details', html, re.S).group(1)
    return [
        (h, label, cur or None)
        for h, cur, label in re.findall(
            r'<a(?: class="nav-cta")? href="([^"]+)"(?: aria-current="([^"]+)")?>([^<]+)</a>', nav
        )
    ]


def _menu(html: str) -> list[str]:
    menu = re.search(r'<div class="menu">(.*?)</div>', html, re.S).group(1)
    return re.findall(r'<a href="([^"]+)"', menu)


@pytest.fixture
def head(tmp_path, monkeypatch):
    monkeypatch.setattr(bcp, "SITE", tmp_path)
    monkeypatch.setattr(bcp, "_PG_CSS_WRITTEN", False)
    return bcp.head


def test_the_header_names_majors_and_findings(head):
    html = head("t", "d", "/x/")
    assert [(h, label) for h, label, _ in _nav(html)] == [
        ("/majors/", "Majors"),
        ("/findings/", "Findings"),
        ("/k12/", "High schools"),
        ("/methodology/", "Methodology"),
        ("/about/", "About"),
        ("/value-check/", "Find a college"),
    ]
    assert _menu(html) == ["/majors/", "/findings/", "/k12/", "/methodology/", "/about/"]
    header = re.search(r'<header class="site-header">.*?</header>', html, re.S).group(0)
    assert 'href="/#data"' not in header and 'href="/careers/"' not in header
    # Careers stays reachable: the footer keeps it, beside Majors.
    assert (
        '<a href="/careers/">Careers</a>' in bcp.FOOTER
        and '<a href="/majors/">Majors</a>' in bcp.FOOTER
    )


def test_a_page_marks_its_own_section_in_the_bar_and_the_menu(head):
    html = head("t", "d", "/majors/", current={"/majors/": "page"})
    header = re.search(r'<header class="site-header">.*?</header>', html, re.S).group(0)
    assert header.count('<a href="/majors/" aria-current="page">Majors</a>') == 2
    assert header.count("aria-current") == 2
    assert "aria-current" not in head("t", "d", "/x/").split("</header>")[0]


def test_a_mark_on_a_link_the_header_no_longer_has_stops_the_build(head):
    with pytest.raises(SystemExit, match="appears 0 times"):
        head("t", "d", "/careers/", current={"/careers/": "page"})


def test_the_majors_and_findings_indexes_mark_themselves(tmp_path, monkeypatch):
    import pipeline.build_majors_pages as bm
    import pipeline.build_stats_exposure as bs

    monkeypatch.setattr(bcp, "SITE", tmp_path)
    monkeypatch.setattr(bcp, "_PG_CSS_WRITTEN", False)
    majors = bm.majors_index({})
    assert ("/majors/", "Majors", "page") in _nav(majors)
    findings = bs.render_index()
    assert ("/findings/", "Findings", "page") in _nav(findings)
    for html in (majors, findings):
        assert sum(1 for *_, cur in _nav(html) if cur) == 1


def test_careers_marks_majors_as_its_section():
    html = (SITE / "careers" / "index.html").read_text()
    assert ("/majors/", "Majors", "true") in _nav(html)
    assert html.split("</header>")[0].count('aria-current="true"') == 2
