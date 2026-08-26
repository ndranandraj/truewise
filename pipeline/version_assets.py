"""Stamp the stylesheet link with a content hash so a CSS change busts its own browser cache.

site/_headers caches styles.css for an hour. Without versioning, a returning visitor within an
hour of a CSS-changing deploy gets fresh HTML paired with the stale cached CSS, which renders a
broken layout (the exact symptom seen after the 2026-08 UX deploy). Rewriting every
`<link href="styles.css">` to `styles.css?v=<hash>` makes the URL change whenever, and only
whenever, the CSS changes, forcing a fresh fetch; unchanged CSS keeps its cache. The _headers
path match ignores the query string, so the cache rule still applies.

Runs at deploy, after all pages are generated, over the built site/ tree. It is deliberately NOT
committed into the source HTML: the repo keeps the plain `styles.css` reference, and the deploy
checkout is stamped in place before Wrangler uploads.

Usage:
    python -m pipeline.version_assets
"""

from __future__ import annotations

import hashlib
import re

from pipeline.config import ROOT

SITE = ROOT / "site"
# Both deployed stylesheets are fingerprinted: styles.css (the whole site) and components.css (the
# canonical profile's component styles). A rebrand that changes only components.css must bust only its
# own cache, so each sheet carries an independent ?v=<hash> of its own content.
SHEETS = ("styles.css", "components.css")


def _link_re(name: str) -> re.Pattern:
    # href="name" or href="/name", with or without an existing ?v= stamp.
    return re.compile(rf'href="(/?){re.escape(name)}(?:\?v=[^"]*)?"')


LINK_RES = {name: _link_re(name) for name in SHEETS}


def sheet_hash(name: str) -> str | None:
    """Short content hash of a shipped stylesheet, or None if it is not present."""
    p = SITE / name
    return hashlib.sha256(p.read_bytes()).hexdigest()[:10] if p.exists() else None


def stylesheet_hash() -> str:
    """Content hash of styles.css (kept for callers/tests that stamp the primary sheet)."""
    return sheet_hash("styles.css")


def stamp_sheet(html: str, name: str, ver: str) -> str:
    """Rewrite every reference to `name` to carry ?v=<ver>. Idempotent; touches only that sheet."""
    return LINK_RES[name].sub(rf'href="\g<1>{name}?v={ver}"', html)


def stamp(html: str, ver: str) -> str:
    """Back-compat: stamp styles.css only."""
    return stamp_sheet(html, "styles.css", ver)


def main() -> None:
    versions = {name: sheet_hash(name) for name in SHEETS}
    versions = {name: ver for name, ver in versions.items() if ver}
    changed = 0
    for path in SITE.rglob("*.html"):
        src = path.read_text()
        out = src
        for name, ver in versions.items():
            out = stamp_sheet(out, name, ver)
        if out != src:
            path.write_text(out)
            changed += 1
    stamps = ", ".join(f"{n}?v={v}" for n, v in versions.items())
    print(f"stamped [{stamps}] into {changed} html files")


if __name__ == "__main__":
    main()
