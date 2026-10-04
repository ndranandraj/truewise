"""One table treatment across the site (October 2026).

Every data table family gets the same look: a tinted header band with a 2px base, row padding and
rules, a hover and keyboard-focus row highlight, tabular figures. No stripes, because the profile's
sand tint means "no verdict". Where a table already marks a row with --brand-50 (the Careers degree
being viewed, the Value Check row a link pointed to), hover and focus use a neutral tint instead,
and the marked row gets a leading bar. The Careers current degree is explicit: a class, aria-current
on its link and a visible label, not an inline tint read by colour alone.
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


def test_careers_current_degree_is_explicit_not_colour_alone():
    page = (SITE / "careers" / "index.html").read_text()
    assert 'style="background: var(--brand-50)"' not in page, (
        "the current degree is still an inline tint"
    )
    assert (
        'class="is-current"' in page and 'aria-current="page"' in page and "Current degree" in page
    )
    css = SOURCES["careers"]
    assert ".cred-table tbody tr:not(.is-current):focus-within" in css
    assert (
        ".cred-table tbody tr.is-current > :first-child { box-shadow: inset 3px 0 0 var(--brand); }"
        in css
    )


def test_careers_detail_tables_use_cards_at_enlarged_text():
    css = SOURCES["careers"]
    assert (
        "@container cr-detail (max-width: 44em)" in css
        and "@container cr-demand (max-width: 36em)" in css
    )
    page = (SITE / "careers" / "index.html").read_text()
    assert 'class="module cr-detail-cq"' in page and 'class="demand cr-demand-cq"' in page
