"""The section links on the finding and on every profile (review of 11 October 2026).

On phones the links ran sideways under a fade, and a link reached by Tab or Shift+Tab stayed partly
under it. The fix: with pipeline/sectnav_script.js the row scrolls a focused link clear, also when a
size changes; without the script the links wrap; and the focus ring is painted inside the link, so it
shows whenever the link does. These tests hold the parts that can be read from the source. The
behaviour itself (real Tab and Shift+Tab in Chromium and Firefox, normal and 200% text, reduced motion,
JavaScript off, the script failing, the screen's edges, resizing with focus kept) is
tests/sectnav_focus.js, against a built site.
"""

from __future__ import annotations

import re

from pipeline.build_college_pages import SECTNAV_JS, sectnav_script
from pipeline.config import ROOT

CSS = (ROOT / "site" / "article.css").read_text()
SRC = (ROOT / "pipeline" / "sectnav_script.js").read_text()


def _rules(css: str) -> list[tuple[str | None, str, str]]:
    """(media condition or None, selector, declarations) for each rule."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, top = [], []
    i = 0
    while (m := re.compile(r"@media([^{]*)\{").search(css, i)) is not None:
        top.append(css[i : m.start()])
        depth, j = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        body = css[m.end() : j - 1]
        out += [
            (m[1].strip(), sel.strip(), d) for sel, d in re.findall(r"([^{}]+)\{([^{}]*)\}", body)
        ]
        i = j
    top.append(css[i:])
    out += [(None, sel.strip(), d) for sel, d in re.findall(r"([^{}]+)\{([^{}]*)\}", "".join(top))]
    return out


PHONE = "(max-width: 767px)"


def test_without_the_script_the_links_wrap_and_nothing_pins_or_scrolls():
    """Every rule that makes the row scroll, pin, fade or stop wrapping needs .sectnav--scroll, the
    class the script adds; so JavaScript off, or the script failing, leaves the wrapped list."""
    enhancing = ("sticky", "nowrap", "overflow-x", "linear-gradient", "display: none")
    rules = [r for r in _rules(CSS) if "sectnav" in r[1]]
    assert len([r for r in rules if r[0] == PHONE]) >= 6, "the phone rules were not found"
    for media, sel, decl in rules:
        if media == "(min-width: 1200px)":
            continue  # the side rail takes over there
        if media == PHONE or any(k in decl for k in enhancing):
            assert all(".sectnav--scroll" in part for part in sel.split(",")), (
                f"{sel} ({media or 'all widths'}) changes the bar without the script's class"
            )
    base = {sel: d for media, sel, d in rules if media is None}
    assert "flex-wrap: wrap" in base[".sectnav ul"]


def test_the_focus_ring_is_painted_inside_the_link():
    """Moving focus brings at most a link's border box on screen, so only a ring inside that box is
    sure to show: at the screen's edges and the row's, and with JavaScript off (review of 5 November).
    It must stay clear of the words, by more than a near-fit."""
    focus = (ROOT / "site" / "styles.css").read_text()
    width = int(re.search(r":focus-visible \{ outline: (\d+)px solid", focus)[1])
    base = {}
    for media, sel, decl in _rules(CSS):
        if media is None:
            base[sel] = base.get(sel, "") + decl
    offset = int(re.search(r"outline-offset: (-?\d+)px", base[".sectnav a:focus-visible"])[1])
    assert width + offset <= 0, f"the {width}px ring at {offset}px reaches outside the link"
    pad = re.search(r"padding: (\d+)px (\d+)px;", base[".sectnav a"])
    assert min(int(pad[1]), int(pad[2])) >= -offset + 2, "the ring touches, or nearly, the words"


def test_the_scroll_margin_is_enough_and_follows_the_text():
    """Firefox left a link cut by up to 5.5px with a 12px margin, or 12px at 200% text; from 24px none
    was cut (measured 5 November). A px value would be a near-fit as soon as text grows further."""
    base = " ".join(d for media, sel, d in _rules(CSS) if media is None and sel == ".sectnav a")
    margin = re.search(r"scroll-margin-block: ([\d.]+)rem", base)
    assert margin, "the bar's scroll margin must be in rem, so it grows with the text"
    assert float(margin[1]) >= 2, "the scroll margin is below what was measured to be enough"


def test_the_last_link_can_scroll_clear_of_the_fade():
    block = {sel: d for media, sel, d in _rules(CSS) if media == PHONE}
    fade = int(re.search(r"width: (\d+)px", block[".sectnav--scroll .sectnav__scroll::after"])[1])
    gap = int(re.search(r"var GAP = (\d+)", SRC)[1])
    end = int(re.search(r"padding-right: (\d+)px", block[".sectnav--scroll li:last-child"])[1])
    assert end >= fade + gap, f"the last link can scroll only {end}px of {fade + gap}"


def test_the_script_enables_the_row_last_and_never_moves_focus():
    body = SECTNAV_JS.strip().splitlines()
    assert body[-2:] == ['nav.classList.add("sectnav--scroll");', "})();"], (
        "the class must be the last thing the script does, so a failure leaves the wrapped list"
    )
    for banned in (
        ".focus(",
        "preventDefault",
        "tabindex",
        "scrollIntoView",
        "scrollTo",
        "scrollBy",
    ):
        assert banned not in SECTNAV_JS, (
            f"the script must leave focus and the page alone ({banned})"
        )
    # A size change repeats the check, for the link that has focus and for nothing else.
    assert "new ResizeObserver" in SECTNAV_JS and "document.activeElement" in SECTNAV_JS
    assert "list.contains(a)" in SECTNAV_JS, "the row must only act for a link inside it"
    # The guard: a browser without what the script needs keeps the wrapped list.
    assert "!window.requestAnimationFrame" in SECTNAV_JS
    assert sectnav_script() == f"<script>{SECTNAV_JS}</script>"
    assert "{{" not in SECTNAV_JS and "/*" not in SECTNAV_JS and "// " not in SECTNAV_JS


def test_a_link_is_never_wider_than_the_clear_part_of_the_row():
    """Linux Firefox at 200% text set "Look up a college" 245px wide against 238px of clear row on a
    320px screen, so the script could show one end or the other, never both (CI, 8 November)."""
    block = {sel: d for media, sel, d in _rules(CSS) if media == PHONE}
    fade = int(re.search(r"width: (\d+)px", block[".sectnav--scroll .sectnav__scroll::after"])[1])
    gap = int(re.search(r"var GAP = (\d+)", SRC)[1])
    edge = int(re.search(r"EDGE = (\d+)", SRC)[1])
    assert "container-type: inline-size" in block[".sectnav--scroll .sectnav__scroll"]
    cap = re.search(r"max-width: calc\(100cqw - (\d+)px\)", block[".sectnav--scroll a"])
    assert cap and int(cap[1]) >= fade + gap + edge, "a link can be wider than the clear row"
    # Each item keeps its own width, so only a label longer than the cap wraps.
    assert "flex: none" in block[".sectnav--scroll li"]
