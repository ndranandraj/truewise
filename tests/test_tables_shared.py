"""One table treatment across the site (October 2026).

Every data table family gets the same look: a tinted header band with a 2px base, row padding and
rules, a hover and keyboard-focus row highlight, tabular figures. No stripes, because the profile's
sand tint means "no verdict". Where a table already marks a row with --brand-50 (the degree being
viewed on a major and degree page, the Value Check row a link pointed to), hover and focus use a
neutral tint instead, and the marked row gets a leading bar. The degree being viewed is explicit: a
class, aria-current on its link and a visible label, not a tint read by colour alone. Until November
2026 that table was on Careers, in the view a major opened in; the view is now its own page.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline import build_college_pages as bcp

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _nocomments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


SOURCES = {
    "pg.css (generated pages)": _nocomments(bcp.PG_CSS),
    "profile.css": _nocomments((SITE / "profile.css").read_text()),
    "careers": _nocomments((SITE / "careers" / "index.html").read_text()),
    "compare": _nocomments((SITE / "compare" / "index.html").read_text()),
    "k12 compare": _nocomments((SITE / "k12" / "compare" / "index.html").read_text()),
    "value-check": _nocomments((SITE / "value-check" / "index.html").read_text()),
}


def test_every_table_family_has_the_shared_header_band_and_row_highlight():
    for name, css in SOURCES.items():
        assert "border-bottom: 2px solid var(--ink-faint)" in css, f"{name}: no firm header base"
        assert ":focus-within" in css, f"{name}: keyboard focus does not highlight the row"
        assert "tabular-nums lining-nums" in css, f"{name}: figures are not on tabular numerals"


def test_no_striped_rows_anywhere():
    for name, css in SOURCES.items():
        assert not re.search(r"tr:nth-child\((even|odd|2n)", css), (
            f"{name}: striped rows blur the no-verdict tint"
        )


def test_unassessed_rows_keep_their_tint_under_the_pointer():
    css = SOURCES["profile.css"]
    assert "tr:not(.tw-tr--insuf):hover" in css and "tr:not(.tw-tr--insuf):focus-within" in css


def test_the_degree_being_viewed_is_explicit_not_colour_alone():
    from pipeline import build_major_degree_pages as mdp

    f = {
        "cip": "5138",
        "name": "Registered Nursing",
        "cred": "3",
        "credential": "Bachelor's Degree",
    }
    row = {"med": 80000, "p25": 70000, "p75": 90000, "programs": 6}
    siblings = [
        {**f, **row},
        {**f, **row, "cred": "5", "credential": "Master's Degree"},
    ]
    table = mdp.ladder(siblings[0], siblings, "registered-nursing")
    current = [r for r in table.split("<tr")[1:] if 'class="md-cur"' in r]
    assert len(current) == 1, "exactly one row is this page's degree"
    assert 'aria-current="page"' in current[0] and "This page" in current[0]
    assert "style=" not in table, "the current degree must not be an inline tint"
    css = _nocomments((SITE / "article.css").read_text())
    assert (
        ".md table.t tbody tr.md-cur > :first-child { box-shadow: inset 3px 0 0 var(--brand); }"
        in css
    )
    assert (
        "#degrees table.t tbody tr:not(.md-cur):focus-within > * { background: var(--bg-alt); }"
        in css
    )
    assert "#degrees table.t tbody tr:not(.md-cur):hover > *," in css
