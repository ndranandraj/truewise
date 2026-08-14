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
# href="styles.css" or href="/styles.css", with or without an existing ?v= stamp.
LINK_RE = re.compile(r'href="(/?)styles\.css(?:\?v=[^"]*)?"')


def stylesheet_hash() -> str:
    """Short, stable content hash of the shipped stylesheet."""
    return hashlib.sha256((SITE / "styles.css").read_bytes()).hexdigest()[:10]


def stamp(html: str, ver: str) -> str:
    """Rewrite every styles.css reference to carry ?v=<ver>. Idempotent."""
    return LINK_RE.sub(rf'href="\1styles.css?v={ver}"', html)


def main() -> None:
    ver = stylesheet_hash()
    changed = 0
    for path in SITE.rglob("*.html"):
        src = path.read_text()
        out = stamp(src, ver)
        if out != src:
            path.write_text(out)
            changed += 1
    print(f"stamped styles.css?v={ver} into {changed} html files")


if __name__ == "__main__":
    main()
