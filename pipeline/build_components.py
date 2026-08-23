"""Copy the Stage 3/4 component assets into the deployed site (Stage 4.3 serving harness).

The components are authored in isolation under components/ (outside the deployed tree). The canonical
profile and the pilot reference them at site-root paths (/components.css, /components/table.js, ...),
so the build must copy them into site/ or those references 404. Source of truth stays in components/;
this only mirrors the deployable assets.

Usage:
    python -m pipeline.build_components          # copy assets into site/
    python -m pipeline.build_components --check   # exit 1 if the copies are stale (CI guard)
"""

from __future__ import annotations

import argparse
import shutil
import sys

from pipeline.config import ROOT

COMPONENTS = ROOT / "components"
SITE = ROOT / "site"

# (source relative to components/, destination relative to site/)
ASSETS = [
    ("components.css", "components.css"),
    ("table.js", "components/table.js"),
    ("profile.js", "components/profile.js"),
    ("ui.js", "components/ui.js"),
    ("search.js", "components/search.js"),
]


def _pairs():
    for src_rel, dst_rel in ASSETS:
        yield COMPONENTS / src_rel, SITE / dst_rel


def build(check: bool) -> int:
    if check:
        stale = []
        for src, dst in _pairs():
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                stale.append(str(dst.relative_to(ROOT)))
        if stale:
            print(
                "STALE component assets (run `make components`): " + ", ".join(stale),
                file=sys.stderr,
            )
            return 1
        print("components: deployed assets are current")
        return 0

    n = 0
    for src, dst in _pairs():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        n += 1
    print(f"components: copied {n} assets into {SITE.relative_to(ROOT)}/")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if deployed copies are stale")
    args = ap.parse_args()
    sys.exit(build(args.check))


if __name__ == "__main__":
    main()
