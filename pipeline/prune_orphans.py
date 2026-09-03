"""Delete pre-rendered pages that the current build no longer produces.

Why this exists
---------------
The deploy workflow builds every pre-rendered page from scratch on a clean checkout (the
`site/college/` and `site/findings/` trees are gitignored), so production only ever contains pages
the current data produces. A LOCAL working tree is different: it accumulates. When a school's slug
changes or a finding is retired, the old directory stays on disk forever, and `wrangler deploy`
uploads everything under `site/`, so a locally built preview serves pages that production 404s.

That is how thirteen stale pages reached a preview on 2026-09-02: twelve college pages plus
`/findings/data-audit/`. The college ones were stale disambiguation suffixes, the same institutions
being published today under a different slug (`/college/university-of-st-thomas-mn/` versus the
current `/college/university-of-st-thomas/`).

It also matters for the sitemap. `build_sitemap` scans the DISK, so any stray directory would be
published as a real URL on the next build.

Scope
-----
Two trees, each with an authority:

* `/college/` -> `site/college/slug-map.json`, written by the page builder from the current data,
  so its values are exactly the college pages that should exist.
* `/findings/` -> `build_stats_exposure.PUBLISHED_FINDINGS`, the module's own list of what it
  publishes.

NOT covered: `/majors/`, `/lists/`, `/colleges/` and `/updates/`. Those have no published
authority to diff against, and no orphan has been observed in them, but a retired major or list
slug would linger unnoticed the same way. Treat this as a guard on the two trees that have an
authority, not as a whole-site sweep.

Deleting surplus is safe: the check refuses to run unless every expected input is present and every
expected route is already on disk, so a partial or interrupted build can never be mistaken for a
pile of orphans. A missing tree is an error, never a silent pass: reporting "no orphans" for a tree
that was never built would invert the guarantee.

Usage (from repo root):
    python -m pipeline.prune_orphans --check    # list orphans, exit 1 if any (no writes)
    python -m pipeline.prune_orphans            # delete them

Run `--check` before building a preview, so the preview matches what production would serve.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from pipeline.build_stats_exposure import PUBLISHED_FINDINGS
from pipeline.config import ROOT

SITE = ROOT / "site"
COLLEGE = SITE / "college"
FINDINGS = SITE / "findings"
SLUG_MAP = COLLEGE / "slug-map.json"


def _orphans(tree: Path, expected: set[str], label: str) -> list[str]:
    """Directory names under `tree` that `expected` does not claim.

    Raises if the tree looks incomplete rather than stale, so an interrupted build is never
    mistaken for orphans.
    """
    on_disk = {d.name for d in tree.iterdir() if d.is_dir()}
    missing = expected - on_disk
    if missing:
        raise SystemExit(
            f"{len(missing):,} expected {label} route(s) are missing from disk "
            f"(e.g. {sorted(missing)[:3]}). The tree is incomplete, not stale: rebuild first."
        )
    return sorted(on_disk - expected)


def find_orphans(site: Path | None = None) -> list[str]:
    """Every orphaned route, as a site-root path, across both guarded trees.

    Every expected input must be present. A missing tree means the build did not run or did not
    finish, and treating that as "no orphans" would report success on an incomplete tree, which is
    the opposite of the guarantee above. So each absence raises rather than being skipped.

    `site` overrides the site root, for tests.
    """
    site = site or SITE
    college, findings = site / "college", site / "findings"
    slug_map = college / "slug-map.json"

    if not slug_map.exists():
        raise SystemExit(f"no slug map at {slug_map}; run the college page build first")
    if not findings.is_dir():
        raise SystemExit(f"no findings tree at {findings}; run the findings build first")
    if not (findings / "index.html").exists():
        raise SystemExit(
            f"no findings index at {findings / 'index.html'}; the findings build did not finish"
        )

    published = set(json.loads(slug_map.read_text()).values())
    found = [f"/college/{n}/" for n in _orphans(college, published, "college")]
    found += [f"/findings/{n}/" for n in _orphans(findings, set(PUBLISHED_FINDINGS), "findings")]

    # Social cards. A card is orphaned when nothing publishes the route it illustrates. These are
    # PNGs, not directories, so the page sweep above never saw them: ten retired college cards were
    # still returning 200 on a preview while their pages correctly 404'd, which is worse than a
    # stale page, because a card is what gets unfurled into someone's timeline.
    for area in ("college", "majors", "lists", "findings"):
        cards, pages = site / "og" / area, site / area
        if not cards.is_dir() or not pages.is_dir():
            continue
        routed = {d.name for d in pages.iterdir() if d.is_dir()}
        found += [
            f"/og/{area}/{p.name}"
            for p in sorted(cards.glob("*.png"))
            if p.stem not in routed and not p.stem.startswith("_")
        ]
    return found


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
        print("college + findings pages: no orphans, disk matches the published routes")
        return

    for route in orphans:
        print(f"  {route}")
    if args.check:
        raise SystemExit(
            f"{len(orphans):,} orphaned page(s) would ship from a local deploy. "
            "Run `python -m pipeline.prune_orphans` to remove them."
        )
    for route in orphans:
        target = SITE / route.strip("/")
        # Pages are directories, social cards are single PNGs.
        shutil.rmtree(target) if target.is_dir() else target.unlink()
    print(f"pruned {len(orphans):,} orphaned page(s)")


if __name__ == "__main__":
    main()
