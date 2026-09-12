"""Write site/sitemap.xml by scanning the built site for every generated page.

Run this LAST, after the page builders, so the sitemap reflects whatever pages exist on disk
regardless of build order.

Writes a sitemap INDEX at /sitemap.xml pointing at one file per page family, so indexation can be
diagnosed per family in Search Console rather than by classifying thousands of URLs by hand. The
index URL is unchanged, so the submitted sitemap in Search Console keeps working.

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
    "/compare/",
    "/majors/",
    "/k12/",
    "/k12/advanced-courses/",
    "/k12/rankings/",
    "/k12/compare/",
    "/methodology/",
    "/about/",
    "/findings/",
    "/lists/",
    "/updates/",
]


SEGMENTS = [
    ("core", None),  # the hand-written pages, filled from STATIC
    ("college", "/college/"),
    ("colleges", "/colleges/"),
    ("majors", "/majors/"),
    ("lists", "/lists/"),
    ("findings", "/findings/"),
]


def _urlset(urls) -> str:
    body = "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )


def collect() -> dict[str, list[str]]:
    """URLs per page family, in the order a crawler should meet them."""
    seg: dict[str, list[str]] = {name: [] for name, _ in SEGMENTS}
    seg["core"] = [
        f"{BASE}{p}" for p in STATIC if (SITE / p.strip("/") / "index.html").exists() or p == "/"
    ]
    for name, prefix in SEGMENTS:
        if prefix is None:
            continue
        base = SITE / name
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and (d / "index.html").exists():
                seg[name].append(f"{BASE}{prefix}{d.name}/")
    # A URL belongs to exactly one sitemap. /colleges/ is in core AND is a directory, so it would
    # otherwise appear twice and make the per-family counts in Search Console disagree with reality.
    seen = set()
    for name, _ in SEGMENTS:
        kept = []
        for u in seg[name]:
            if u not in seen:
                seen.add(u)
                kept.append(u)
        seg[name] = kept
    return seg


def main() -> None:
    """One sitemap per page family, behind an index at the unchanged /sitemap.xml.

    A single 6,548-URL sitemap is valid and well inside Google's limits, but it makes indexation
    impossible to diagnose: the September baseline showed 4,930 indexed against 6,548 submitted,
    and nothing in Search Console says which families the missing 1,618 are in. Split by family,
    that question is answered by reading one screen instead of classifying thousands of URLs.

    No lastmod. It would have to be honest, and the build has no per-page change history, so a
    build timestamp on every URL would tell a crawler that 6,548 pages changed whenever any did.
    """
    seg = collect()
    index_entries = []
    for name, _ in SEGMENTS:
        urls = seg[name]
        if not urls:
            continue
        (SITE / f"sitemap-{name}.xml").write_text(_urlset(urls))
        index_entries.append(f"  <sitemap><loc>{BASE}/sitemap-{name}.xml</loc></sitemap>")

    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(index_entries)
        + "\n</sitemapindex>\n"
    )
    total = sum(len(v) for v in seg.values())
    parts = ", ".join(f"{n} {len(seg[n]):,}" for n, _ in SEGMENTS if seg[n])
    print(f"sitemap index: {total:,} urls across {len(index_entries)} files ({parts})")


if __name__ == "__main__":
    main()
