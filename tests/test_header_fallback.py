"""The header at enlarged text (October 2026 accessibility repair).

At 200% text-only enlargement the header row no longer fitted: the tagline was drawn over the links,
"Find a college" ran off-screen, and on phones the menu button was pushed off-screen, so navigation
could not be reached. The header script now measures and steps through fallbacks; pinned elements
follow the header's measured height; nothing pins without the script. The browser behaviour is
checked by the layout check's enlarged-text pass; these pin the pieces it depends on.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from pipeline import build_college_pages as bcp

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def _css(name: str) -> str:
    return re.sub(r"/\*.*?\*/", "", (SITE / name).read_text(), flags=re.S)


def test_head_inlines_the_header_script_with_todays_behaviour_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(bcp, "SITE", tmp_path)
    monkeypatch.setattr(bcp, "_PG_CSS_WRITTEN", False)
    html = bcp.head("t", "d", "/x/")
    header = re.search(r'<header class="site-header">.*?</header>', html, re.S).group(0)
    script = re.search(r"<script>(.*?)</script>", header, re.S).group(1)
    for step in (
        "hdr-tight",
        "hdr-collapsed",
        "hdr-wrap",
        "hdr-unstick",
        "pin-ok",
        "--hdr-h",
        "--pin-h",
    ):
        assert step in script, f"header script lost {step}"
    # Today's behaviour: Escape closes the menu, a click outside closes it, tables get card labels.
    assert '"Escape"' in script and "nav-toggle[open]" in script and "table.t" in script
    # Focus is remembered on focusin, and a focused menu link is revealed instantly.
    assert '"focusin"' in script and 'behavior: "instant"' in script
    assert "/*" not in script, "comments should be stripped from the inlined script"


def test_hand_written_pages_carry_the_same_header():
    out = subprocess.run(
        [sys.executable, "-m", "pipeline.sync_header", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr


def test_header_states_and_pinning_rules_exist():
    css = _css("styles.css")
    for rule in (
        ".site-header.hdr-tight .brand-tagline { display: none; }",
        ".site-header.hdr-collapsed nav > a:not(.nav-cta) { display: none; }",
        ":root:not(.pin-ok) .site-header,",
        ":root:not(.pin-ok) .sectnav, :root:not(.pin-ok) .subnav { position: static; }",
        ":root { scroll-padding-top: calc(var(--pin-h, 0px) + 12px); }",
    ):
        assert rule in css, f"styles.css lost: {rule}"
    assert "top: calc(var(--hdr-h, 0px) + 31px)" in css, (
        "the rail must pin below the measured header"
    )


def test_no_fixed_header_offsets_remain():
    """Fixed 65px and 96px offsets and scroll-margin guesses assumed today's header height."""
    files = [SITE / n for n in ("styles.css", "article.css", "home.css", "profile.css")]
    files += [SITE / "k12" / "index.html"] + sorted((SITE / "k12").glob("*/index.html"))
    for f in files:
        text = re.sub(r"/\*.*?\*/", "", f.read_text(), flags=re.S)
        assert not re.search(r"top: ?(65|96)px", text), f"{f.name}: fixed header offset"
        assert "scroll-margin-top" not in text, f"{f.name}: fixed anchor margin"
