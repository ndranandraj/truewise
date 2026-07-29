"""Write site/sitemap.xml by scanning the built site for every generated page.

Run this LAST, after the page builders (build_college_pages, build_majors_pages), so the
sitemap always reflects whatever pages exist on disk regardless of build order. Includes the
fixed static pages plus every /college/<slug>/, /colleges/<state>/, and /majors/<slug>/ page.

Usage (from repo root):
    python -m pipeline.build_sitemap
"""

from __future__ import annotations

from pipeline.config import ROOT

SITE = ROOT / "site"
BASE = "https://truewise.dev"

STATIC = [
    "/",
    "/value-check/",
    "/careers/",
    "/colleges/",
    "/majors/",
    "/k12/",
    "/k12/advanced-courses/",
    "/k12/rankings/",
    "/k12/compare/",
    "/methodology/",
    "/about/",
    "/findings/",
    "/lists/",
]


def main() -> None:
    urls = [
        f"{BASE}{p}" for p in STATIC if (SITE / p.strip("/") / "index.html").exists() or p == "/"
    ]
    for parent, prefix in (
        ("college", "/college/"),
        ("colleges", "/colleges/"),
        ("majors", "/majors/"),
        ("findings", "/findings/"),
        ("lists", "/lists/"),
    ):
        base = SITE / parent
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                urls.append(f"{BASE}{prefix}{d.name}/")

    # De-dupe while preserving order (e.g. /colleges/ static + state dirs).
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in ordered)
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )
    print(f"sitemap: {len(ordered):,} urls -> {SITE / 'sitemap.xml'}")


if __name__ == "__main__":
    main()
