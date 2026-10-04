"""The site frame (Prototype G, approved October 2026): wide pages share an 8-column main area beside a
4-column side area from 1100px. These pin what each page relies on; the browser layout check measures
the result."""

from __future__ import annotations

import re
from pathlib import Path

from pipeline.build_canonical_profiles import _notes_aside

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _css(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_shared_frame_tokens_and_side_panel():
    css = _css((SITE / "styles.css").read_text())
    assert ":root { --frame-gap: var(--s7); }" in css
    assert ".side-panel { border-top: 2px solid var(--ink);" in css


def test_homepage_examples_sit_beside_the_search():
    html = (SITE / "index.html").read_text()
    hero = html.split('<section class="h-hero"', 1)[1].split("</section>", 1)[0]
    # Search stays first in the hero; the examples follow it, in the side panel.
    assert (
        hero.index('class="h-main"')
        < hero.index('class="h-search"')
        < hero.index("h-side side-panel")
    )
    assert '<h2 id="ex-h" class="side-panel__h">What a result looks like</h2>' in hero
    assert hero.count('<li class="ex__row') == 3
    # The old section and its rules are gone, so nothing styles a block that no longer exists.
    assert "h-examples" not in html
    home = _css((SITE / "home.css").read_text())
    assert "h-examples" not in home
    # .home h2 is a display-size heading; the panel label must restate its own type to win.
    assert re.search(r"\.home \.side-panel__h \{[^}]*font-size: var\(--t-label\)", home)
    wide = home.split("@media (min-width: 1100px)", 1)[1]
    assert "grid-template-columns: minmax(0, 8fr) minmax(0, 4fr)" in wide


def test_k12_note_follows_the_tiles_and_sits_beside_the_intro_when_wide():
    html = (SITE / "k12" / "index.html").read_text()
    main = html.split('<main class="wrap k-hub">', 1)[1].split("</main>", 1)[0]
    # Phones and screen readers reach the tools before the source note.
    assert (
        main.index('class="k-hero"')
        < main.index('class="live-modules"')
        < main.index("k-side side-panel")
    )
    assert 'aria-labelledby="k-side-h"' in main and 'id="k-side-h">About the data</p>' in main
    css = _css(html.split("<style>", 1)[1].split("</style>", 1)[0])
    assert ".k-hub > .k-side { grid-column: 2; grid-row: 1;" in css
    assert ".k-hub > .live-modules { grid-column: 1 / -1; grid-row: 2; }" in css
    # The 1 in 4 sentence keeps its qualifier.
    assert (
        "a count that includes alternative, special-education and juvenile-justice schools"
        in re.sub(r"\s+", " ", main)
    )


def test_careers_list_is_cards_rather_than_a_squeezed_or_scrolling_table():
    html = (SITE / "careers" / "index.html").read_text()
    css = _css(html.split("<style>", 1)[1].split("</style>", 1)[0])
    # Both the script's list and the no-JavaScript table are containers.
    assert "#list, #boot-fallback { container: cr-list / inline-size; }" in css
    assert "@container cr-list (max-width: 60em)" in css
    # Headers and figures stay on one line in the table: nothing lets them wrap.
    assert not re.search(r"\.cr-table thead th \{[^}]*white-space: normal", css)
    assert '<div id="boot-fallback">' in html and '<div id="list"></div>' in html


def test_profile_notes_are_one_group_and_absent_when_there_are_none():
    assert _notes_aside("") == ""
    out = _notes_aside('      <p class="note">A note.</p>\n')
    assert out.startswith('      <aside class="progs__aside" aria-label="Reading the table">')
    assert '<p class="note">A note.</p>' in out and out.rstrip().endswith("</aside>")
    page = SITE / "college" / "university-of-california-los-angeles" / "index.html"
    if page.exists():  # built pages are not in the repo
        progs = page.read_text().split('<section id="programs"', 1)[1].split("</section>", 1)[0]
        assert (
            progs.index('<h2 id="programs-h">')
            < progs.index("progs__aside")
            < progs.index("data-tw-profile")
        )
