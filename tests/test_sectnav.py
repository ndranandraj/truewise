"""The section links on the finding and on every profile (review of 11 October 2026).

On phones the links ran sideways under a fade, and a link reached by Tab or Shift+Tab stayed partly
under it. The fix: with pipeline/sectnav_script.js the row scrolls and a focused link, ring included,
is moved clear; without the script the links wrap. These tests hold the parts that can be read from
the source. The behaviour itself (real Tab and Shift+Tab in Chromium and Firefox, normal and 200%
text, reduced motion, JavaScript off, the script failing) is tests/sectnav_focus.js, against a built
site.
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


def test_the_ring_has_room_at_both_ends():
    """The scroller clips, so the first link's ring needs padding inside it, and the last link must
    be able to scroll its ring clear of the fade with the script's gap."""
    block = {sel: d for media, sel, d in _rules(CSS) if media == PHONE}
    focus = (ROOT / "site" / "styles.css").read_text()
    m = re.search(
        r":focus-visible \{ outline: (\d+)px solid [^;]+; outline-offset: (\d+)px;", focus
    )
    ring = int(m[1]) + int(m[2])
    pad = re.search(r"padding: (\d+)px (\d+)px (\d+)px;", block[".sectnav--scroll ul"])
    # A margin beyond the ring, not a near-fit: text and subpixels measure differently on Linux.
    edge = int(re.search(r"EDGE = (\d+);", SRC)[1])
    assert edge >= 2 and int(pad[1]) >= ring + edge and int(pad[2]) >= ring + edge, (
        "the ring is clipped, or only just fits, at the row's edges"
    )
    assert f"margin: 0 -{pad[2]}px" in block[".sectnav--scroll .sectnav__scroll"], (
        "the wrapper must give the padding back, or the chips move"
    )
    fade = int(re.search(r"width: (\d+)px", block[".sectnav--scroll .sectnav__scroll::after"])[1])
    gap = int(re.search(r"var GAP = (\d+)", SRC)[1])
    end = int(re.search(r"padding-right: (\d+)px", block[".sectnav--scroll li:last-child"])[1])
    assert end >= fade + gap + ring, f"the last link can scroll only {end}px of {fade + gap + ring}"


def test_the_script_enables_the_row_last_and_never_moves_focus():
    body = SECTNAV_JS.strip().splitlines()
    assert body[-2:] == ['nav.classList.add("sectnav--scroll");', "})();"], (
        "the class must be the last thing the script does, so a failure leaves the wrapped list"
    )
    for banned in (".focus(", "preventDefault", "tabindex", "scrollIntoView"):
        assert banned not in SECTNAV_JS, f"the script must leave native focus alone ({banned})"
    # The guard: a browser without what the script needs keeps the wrapped list.
    assert "!window.requestAnimationFrame" in SECTNAV_JS
    assert sectnav_script() == f"<script>{SECTNAV_JS}</script>"
    assert "{{" not in SECTNAV_JS and "/*" not in SECTNAV_JS and "// " not in SECTNAV_JS
