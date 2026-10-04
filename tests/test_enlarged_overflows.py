"""Page overflows outside the tables at enlarged text (October 2026).

With doubled text, the FVT/GE association boxes widened a 320px page by 76px, the Careers detail
figures by 25px, article headings and source notes by long words, and file paths and a DOI link on
methodology and findings by up to 217px. The Value Check fallback's Sort select ran 77px off a 390px
screen at normal size. The layout check's enlarged-text pass now fails any page wider than the screen
(pageEnlargedProbe); these pin the rules that keep each case fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _css(rel: str) -> str:
    return re.sub(r"/\*.*?\*/", "", (SITE / rel).read_text(), flags=re.S)


def test_fvtge_boxes_let_the_label_move_below_the_figure():
    css = _css("article.css")
    m = re.search(r"@media \(max-width: 520px\) \{\n  \.stats \{.*?\n\}", css, re.S)
    assert m, "the phone block for the association boxes is missing"
    phone = m.group(0)
    assert ".stats { grid-template-columns: minmax(0, 1fr); }" in phone
    assert (
        "display: flex; flex-wrap: wrap" in phone
        and ".stat__lab { margin: 0; flex: 1 1 0; }" in phone
    )
    assert ".art h1, .chart-src { overflow-wrap: break-word; }" in css


def test_careers_detail_figures_and_phone_cards_respond_to_text_size():
    page = _css("careers/index.html")
    assert ".headline { container: cr-head / inline-size; }" in page
    head = page.split("@container cr-head (max-width: 12em)", 1)[1].split("}\n    }", 1)[0]
    assert "font-size: 1.5rem" in head and "overflow-wrap: anywhere" in head
    assert "@container cr-card (max-width: 12em)" in page
    assert "container: cr-card / inline-size" in page


def test_value_check_fallback_search_and_sort_may_wrap():
    page = _css("value-check/index.html")
    assert ".vc-tools { display: flex; gap: 8px; flex-wrap: wrap; }" in page
    assert ".vc-tools select { max-width: 100%; min-width: 0; }" in page


def test_long_words_paths_and_links_may_break_in_prose():
    css = _css("styles.css")
    assert ":where(.art, .doc, .pg) code { overflow-wrap: anywhere; }" in css
    assert ":where(.art, .doc, .pg) a { overflow-wrap: break-word; }" in css
    assert ".h-hero h1, .h-band__stat { overflow-wrap: break-word; }" in _css("home.css")


def test_layout_check_fails_pages_wider_than_the_screen_at_enlarged_text():
    probe = (ROOT / "tests" / "layout_probe.js").read_text()
    check = (ROOT / "tests" / "layout_check.js").read_text()
    assert (
        "function pageEnlargedProbe()" in probe
        and '"page-enlarged-overflow", blocking: true' in probe
    )
    assert "probes: [headerProbe, tableEnlargedProbe, pageEnlargedProbe]" in check
