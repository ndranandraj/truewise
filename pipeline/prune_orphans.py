"""Delete pre-rendered college pages that the current build no longer produces.

Why this exists
---------------
The deploy workflow builds every pre-rendered page from scratch on a clean checkout (the
`site/college/` tree is gitignored), so production only ever contains pages the current data
produces. A LOCAL working tree is different: it accumulates. When a school's slug changes, the
old directory stays on disk forever, and `wrangler deploy` uploads everything under `site/`, so a
locally built preview serves duplicate pages that production correctly 404s.

That is how `/college/university-of-st-thomas-mn/` and nine others reached a preview on
2026-09-02 while production returned 404 for them. They were stale disambiguation suffixes: the
same institutions are published today at `/college/university-of-st-thomas/` and friends.

It also matters for the sitemap. `build_sitemap` scans the DISK, so any stray directory would be
published as a real URL on the next build.

The authority
-------------
`site/college/slug-map.json` maps unitid -> published slug and is written by the page builder from
the current data, so its values are exactly the set of college pages that should exist. Anything
else in `site/college/` is surplus. Deleting surplus is safe: the check below refuses to run
unless every mapped slug is present on disk, so a partial or interrupted build can never be
mistaken for a pile of orphans.

Scope: `/college/` only. That is where the authoritative map exists and where every orphan has
been observed. The majors, lists and findings trees are small and rebuilt wholesale.

Usage (from repo root):
    python -m pipeline.prune_orphans --check    # list orphans, exit 1 if any (no writes)
    python -m pipeline.prune_orphans            # delete them

Run `--check` before building a preview, so the preview matches what production would serve.
"""

from __future__ import annotations

import argparse
import json
import shutil

from pipeline.config import ROOT

SITE = ROOT / "site"
COLLEGE = SITE / "college"
SLUG_MAP = COLLEGE / "slug-map.json"


def find_orphans() -> list[str]:
    """Directory names under site/college that the current slug map does not claim.

    Raises if the tree looks incomplete rather than stale, so an interrupted build is never
    mistaken for orphans.
    """
    if not SLUG_MAP.exists():
        raise SystemExit(f"no slug map at {SLUG_MAP}; run the college page build first")
    published = set(json.loads(SLUG_MAP.read_text()).values())
    on_disk = {d.name for d in COLLEGE.iterdir() if d.is_dir()}
    missing = published - on_disk
    if missing:
        raise SystemExit(
            f"{len(missing):,} mapped slugs are missing from disk (e.g. {sorted(missing)[:3]}). "
            "The tree is incomplete, not stale: rebuild the college pages before pruning."
        )
    return sorted(on_disk - published)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="report orphans and exit 1 if any exist; make no changes",
    )
    args = ap.parse_args()

    orphans = find_orphans()
    if not orphans:
        print("college pages: no orphans, disk matches the slug map")
        return

    for name in orphans:
        print(f"  /college/{name}/")
    if args.check:
        raise SystemExit(
            f"{len(orphans):,} orphaned college page(s) would ship from a local deploy. "
            "Run `python -m pipeline.prune_orphans` to remove them."
        )
    for name in orphans:
        shutil.rmtree(COLLEGE / name)
    print(f"pruned {len(orphans):,} orphaned college page(s)")


if __name__ == "__main__":
    main()
