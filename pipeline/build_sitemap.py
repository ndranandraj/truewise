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

from datetime import date, datetime

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
    "/earnings-test/",
    "/about/",
    "/about/embed/",
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


# lastmod (Prototype S, approved 22 November 2026): a date only where an honest one exists, never
# the build date, which would tell a crawler that every page changed whenever any did.
#   * Data pages (profiles, state pages, majors, lists): the later of the Scorecard release their
#     figures come from and FAMILY_UPDATED for the family.
#   * Findings: the FVT/GE finding's own UPDATED_ON; a finding without a dateline, the release.
#   * Hand-written pages ("core"): none. The deploy checks out one commit, with no file history to
#     date them from, and a guess would be worse than nothing.
# FAMILY_UPDATED is moved BY HAND, to the day a change to the whole family's wording, figures or
# presentation goes live (the rule the FVT/GE finding's UPDATED_ON follows). "" means the release
# date alone. The build stops on a date in the future.
FAMILY_UPDATED: dict[str, str] = {"college": "", "colleges": "", "majors": "", "lists": ""}


def _iso(value: str) -> str:
    """'2026-06-10' or '2 Oct 2026' as an ISO date; anything else stops the build."""
    for fmt in ("%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise SystemExit(f"build_sitemap: not a date: {value!r}")


def lastmods() -> dict[str, object]:
    """The dates each family's addresses carry: a date for a whole family, or a function of the
    address (findings), or None (no lastmod). Every other family is a data family and carries
    out["data"], the release, so a family added later (the major-and-degree pages) is dated too."""
    from pipeline.build_canonical_profiles import SCORECARD_RELEASE
    from pipeline.build_fvtge import UPDATED_ON

    release = _iso(SCORECARD_RELEASE)
    today = date.today().isoformat()
    out: dict[str, object] = {"core": None, "data": release}
    for family, when in FAMILY_UPDATED.items():
        d = max(release, _iso(when)) if when else release
        if d > today:
            raise SystemExit(f"build_sitemap: {family} is dated {d}, after today")
        out[family] = d
    fvtge = _iso(UPDATED_ON)
    out["findings"] = lambda url: fvtge if url.endswith("/findings/fvtge-reporting/") else release
    return out


def _urlset(urls, when=None) -> str:
    def row(u):
        d = when(u) if callable(when) else when
        return f"  <url><loc>{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>"

    body = "\n".join(row(u) for u in urls)
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

    lastmod only where an honest date exists (see FAMILY_UPDATED above): a build timestamp on every
    URL would tell a crawler that 6,548 pages changed whenever any did.
    """
    seg = collect()
    dates = lastmods()
    index_entries = []
    for name, _ in SEGMENTS:
        urls = seg[name]
        if not urls:
            continue
        (SITE / f"sitemap-{name}.xml").write_text(_urlset(urls, dates.get(name, dates["data"])))
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
