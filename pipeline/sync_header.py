"""Copy the shared site header into the hand-written pages.

Generated pages get their header from head() in build_college_pages.py. The hand-written pages
(homepage, Careers, Compare, K-12, methodology, about, findings, ...) carry a copy, and
tests/test_ui_regressions.py fails if any copy differs. This rewrites each copy from head(), keeping
the one thing a page sets for itself: aria-current="page" on the links to its own section.

    python3 -m pipeline.sync_header           # rewrite the copies
    python3 -m pipeline.sync_header --check   # exit 1 if any copy differs
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from pipeline import build_college_pages as bcp
from pipeline.config import ROOT

SITE = ROOT / "site"
# Built by generators that call head() (they get the header when rebuilt), or local-only folders.
GENERATED = re.compile(
    r"^(college|colleges|majors|lists|og|embed|findings|updates|_proto|_measure)/"
)
HEADER = re.compile(r'<header class="site-header">.*?</header>', re.S)


def reference() -> str:
    # head() writes pg.css as a side effect; point it at a scratch folder.
    with tempfile.TemporaryDirectory() as tmp:
        site, written = bcp.SITE, bcp._PG_CSS_WRITTEN
        bcp.SITE, bcp._PG_CSS_WRITTEN = Path(tmp), False
        try:
            html = bcp.head("t", "d", "/x/")
        finally:
            bcp.SITE, bcp._PG_CSS_WRITTEN = site, written
    return HEADER.search(html).group(0)


def localise(header: str, current: dict[str, str]) -> str:
    """Mark the page's own section links as the page's copy did, with the same value ("page" for the
    section's own page, "true" for a page inside the section, as on the K-12 subpages)."""
    for href, value in current.items():
        header = re.sub(
            rf'(<a\b[^>]*\bhref="{re.escape(href)}")(?![^>]*aria-current)([^>]*>)',
            rf'\1 aria-current="{value}"\2',
            header,
        )
    return header


def pages() -> list[Path]:
    """Hand-written pages only. Generated folders are excluded by name rather than by asking git, so
    this behaves the same in a clean copy without .git (the gate's CI-like test run)."""
    out = []
    for page in sorted(SITE.rglob("*.html")):
        rel = page.relative_to(SITE).as_posix()
        if GENERATED.match(rel):
            continue
        if HEADER.search(page.read_text(errors="ignore")):
            out.append(page)
    return out


def main() -> None:
    check = "--check" in sys.argv
    ref = reference()
    stale = []
    for page in pages():
        text = page.read_text()
        old = HEADER.search(text).group(0)
        current = dict(re.findall(r'<a\b[^>]*\bhref="([^"]+)"[^>]*aria-current="([^"]+)"', old))
        new = localise(ref, current)
        if new != old:
            stale.append(page.relative_to(SITE).as_posix())
            if not check:
                page.write_text(text.replace(old, new, 1))
    if check and stale:
        raise SystemExit("header out of sync: " + ", ".join(stale))
    print(f"header: {len(stale)} page(s) {'out of sync' if check else 'updated'}")


if __name__ == "__main__":
    main()
