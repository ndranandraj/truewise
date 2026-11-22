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

Scripts are stamped the same way (Prototype S, November 2026), and every fingerprinted file is
cached for a year, immutable, in site/_headers. That is only safe while every reference carries the
file's current hash: an unstamped one would be served an old file for a year. `--check` reads the
built site and fails on any reference to a fingerprinted file without its current hash; the deploy
runs it after stamping.

Usage:
    python -m pipeline.version_assets
    python -m pipeline.version_assets --check
"""

from __future__ import annotations

import hashlib
import re

from pipeline.config import ROOT

SITE = ROOT / "site"
# Every deployed stylesheet is fingerprinted: styles.css (the whole site), components.css (the
# canonical profile's component styles), pg.css (the generated pages), article.css (finding and
# profile pages), profile.css (profile pages) and home.css (the homepage). A change to one must
# bust only its own cache, so each sheet carries an independent ?v=<hash> of its own content.
SHEETS = ("styles.css", "components.css", "pg.css", "article.css", "profile.css", "home.css")
# The scripts pages load from the site itself. A file listed here that a build does not have (the
# homepage suggestions arrive with their own PR) is skipped, as an absent stylesheet is.
SCRIPTS = (
    "components/table.js",
    "components/profile.js",
    "components/search.js",
    "assets/college-search.js",
    "assets/home-search.js",
)
FINGERPRINTED = SHEETS + SCRIPTS


def _link_re(name: str) -> re.Pattern:
    # href="name" or href="/name" (src= for a script), with or without an existing ?v= stamp.
    attr = "src" if name.endswith(".js") else "href"
    return re.compile(rf'{attr}="(/?){re.escape(name)}(?:\?v=[^"]*)?"')


LINK_RES = {name: _link_re(name) for name in FINGERPRINTED}


def sheet_hash(name: str, site=None) -> str | None:
    """Short content hash of a shipped stylesheet or script, or None if it is not present."""
    p = (site or SITE) / name
    return hashlib.sha256(p.read_bytes()).hexdigest()[:10] if p.exists() else None


def stylesheet_hash() -> str:
    """Content hash of styles.css (kept for callers/tests that stamp the primary sheet)."""
    return sheet_hash("styles.css")


def stamp_sheet(html: str, name: str, ver: str) -> str:
    """Rewrite every reference to `name` to carry ?v=<ver>. Idempotent; touches only that file."""
    attr = "src" if name.endswith(".js") else "href"
    return LINK_RES[name].sub(rf'{attr}="\g<1>{name}?v={ver}"', html)


def stamp(html: str, ver: str) -> str:
    """Back-compat: stamp styles.css only."""
    return stamp_sheet(html, "styles.css", ver)


def stale_references(site=None) -> list[str]:
    """Every reference in the built site to a fingerprinted file that does not carry the file's
    current hash ("page: name?v=old" or "page: name" for none). The year-long cache in _headers is
    only safe when this is empty."""
    site = site or SITE
    versions = {n: v for n, v in ((n, sheet_hash(n, site)) for n in FINGERPRINTED) if v}
    bad = []
    for path in sorted(site.rglob("*.html")):
        rel = path.relative_to(site).as_posix()
        if rel.startswith(("_proto/", "_measure/")):
            continue
        html = path.read_text(errors="replace")
        for name, ver in versions.items():
            for m in re.finditer(rf'(?:href|src)="/?{re.escape(name)}(\?v=[^"]*)?"', html):
                if m.group(1) != f"?v={ver}":
                    bad.append(f"{rel}: {name}{m.group(1) or ''}")
    return bad


def main() -> None:
    import sys

    if "--check" in sys.argv:
        bad = stale_references()
        if bad:
            raise SystemExit(
                f"version_assets: {len(bad)} references to year-cached files without their current "
                "hash (each would be served an old file for a year):\n  " + "\n  ".join(bad[:30])
            )
        print("version_assets: every reference to a fingerprinted file carries its current hash")
        return
    versions = {name: sheet_hash(name) for name in FINGERPRINTED}
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
