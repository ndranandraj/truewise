"""Guard the UI/UX fixes from 2026-08 so they cannot silently regress.

These are static checks on the shipped source (no data build needed), covering the three
highest-impact fixes: the .verdict class collision that broke ~5,254 pages, the responsive
table wrapper, the cache-control _headers file, and the search hardening.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PIPELINE = ROOT / "pipeline"

# The one primary-nav order every page must share (links before the mobile menu).
CANONICAL_NAV = ["/careers/", "/k12/", "/#data", "/methodology/", "/about/", "/value-check/"]

GENERATORS = [
    "build_college_pages.py",
    "build_majors_pages.py",
    "build_lists.py",
    "build_stats_exposure.py",
]


def test_styles_has_no_bare_verdict_rule():
    """styles.css .verdict (a nowrap pill) collided with the generated headline paragraph
    that also uses .verdict, forcing white-space:nowrap onto a block and blowing the layout
    off-screen on every college/major/findings/updates page. The pill must stay renamed."""
    css = (SITE / "styles.css").read_text()
    assert ".verdict {" not in css, "styles.css .verdict collides with the generated page class"
    assert ".verdict-pill {" in css, "the example-card pill should be .verdict-pill"
    # The homepage is the only user of the pill; it must use the renamed class.
    home = (SITE / "index.html").read_text()
    assert 'class="verdict up"' not in home and 'class="verdict down"' not in home
    assert "verdict-pill" in home


def test_wide_tables_are_wrapped_for_horizontal_scroll():
    """Every generated data table sits in a .tscroll container so it scrolls inside its box
    on a phone instead of pushing the whole page wider than the viewport."""
    head_css = (PIPELINE / "build_college_pages.py").read_text()
    assert ".tscroll" in head_css, "the shared head() must define .tscroll"
    for gen in GENERATORS:
        src = (PIPELINE / gen).read_text()
        opens = src.count('<div class="tscroll"><table class="t')
        closes = src.count("</tbody></table></div>")
        assert opens > 0, f"{gen} should wrap its tables in .tscroll"
        assert opens == closes, (
            f"{gen} has unbalanced tscroll wrappers ({opens} open, {closes} close)"
        )
    # No table may be emitted outside a wrapper.
    for gen in GENERATORS:
        src = (PIPELINE / gen).read_text()
        assert src.count('<table class="t') == src.count('<div class="tscroll"><table class="t')


def test_headers_file_sets_cache_control_with_single_splat_paths():
    """Cloudflare Workers static assets default to max-age=0 (no browser caching). The
    _headers file fixes that, and Workers allows only ONE splat per URL pattern, so the data
    paths must be listed explicitly rather than as /*/data/*."""
    headers = (SITE / "_headers").read_text()
    assert "Cache-Control: public, max-age=3600" in headers
    # Only URL rule lines matter (path lines start with "/"); comment lines starting with "#"
    # may mention /*/data/* as documentation.
    rule_lines = [ln.strip() for ln in headers.splitlines() if ln.strip().startswith("/")]
    assert any(ln == "/value-check/data/*" for ln in rule_lines)
    for ln in rule_lines:
        if "*" in ln:
            assert ln.count("*") == 1, f"Workers _headers allows only one splat per URL: {ln}"


def test_completion_rate_zero_is_treated_as_missing():
    """ED writes literal 0 in C150_4 for schools with no first-time full-time cohort, which we
    once published as "0% complete their program" on 56 real institutions, one of which reports
    earnings for 14,229 graduates on the same page. build_spine must NULLIF it away, and the
    published parquet must contain no zeros."""
    spine = (PIPELINE / "build_spine.py").read_text()
    assert "NULLIF" in spine and "completion_4yr" in spine, "completion coalesce must NULLIF zeros"
    validate = (ROOT / "analysis" / "validate.py").read_text()
    assert "check_completion_not_zero" in validate, "the data-quality gate must assert this"
    assert "completion_rate_never_zero" in validate, "the gate must be registered in main()"

    parquet = ROOT / "published" / "institutions.parquet"
    if parquet.exists():
        import duckdb

        con = duckdb.connect()
        n = con.execute(
            f"SELECT count(*) FROM read_parquet('{parquet}') WHERE completion_rate = 0"
        ).fetchone()[0]
        assert n == 0, f"{n} schools still carry a completion rate of exactly 0"


def test_stylesheet_versioning_stamps_and_is_idempotent():
    """The deploy stamps styles.css with a content hash so a CSS change busts its own cache.
    Guard that it rewrites both relative and absolute refs and never double-stamps."""
    from pipeline import version_assets as va

    ver = va.stylesheet_hash()
    assert re.fullmatch(r"[0-9a-f]{10}", ver), "hash should be 10 hex chars"
    once = va.stamp('<link rel="stylesheet" href="styles.css" /><link href="/styles.css">', ver)
    assert f'href="styles.css?v={ver}"' in once
    assert f'href="/styles.css?v={ver}"' in once
    # Running it again must not append a second ?v=.
    assert va.stamp(once, ver) == once
    # A new hash replaces the old stamp rather than stacking.
    assert va.stamp(once, "deadbeef01").count("?v=") == once.count("?v=")


def _primary_nav_order(html: str) -> list[str]:
    """The hrefs of the primary nav, up to the mobile <details> menu (which repeats them)."""
    nav = re.search(r'<nav aria-label="Primary">(.*?)(?:<details|</nav>)', html, re.S)
    assert nav, "no primary nav found"
    return re.findall(r'<a[^>]*href="([^"]+)"', nav.group(1))


def test_every_page_shares_one_header_nav():
    """The primary CTA used to jump sides and About vanished on some pages. Every hand-written
    page and the generated-page template must now carry the same nav in the same order."""
    static = [
        "index.html",
        "value-check/index.html",
        "careers/index.html",
        "k12/index.html",
        "compare/index.html",
        "about/index.html",
        "methodology/index.html",
    ]
    for rel in static:
        html = (SITE / rel).read_text()
        assert _primary_nav_order(html) == CANONICAL_NAV, f"{rel} nav differs from canonical"
        assert 'class="nav-toggle"' in html, f"{rel} is missing the mobile menu"
    # The generated-page template (college/majors/lists/findings/updates) too.
    gen = (PIPELINE / "build_college_pages.py").read_text()
    assert _primary_nav_order(gen) == CANONICAL_NAV, "generator nav differs from canonical"
    assert 'class="nav-toggle"' in gen, "generator template missing the mobile menu"


def test_search_is_hardened_with_tokens_ranking_aliases_and_empty_state():
    """The college search must not regress to a bare substring filter. Guard the token
    ranking, the alias map, the routed empty state, and the a11y wiring."""
    vc = (SITE / "value-check" / "index.html").read_text()
    assert "SEARCH_ALIASES" in vc, "alias map missing"
    assert "function searchSchools" in vc, "ranked search function missing"
    assert "function detectState" in vc and "emptyStateHTML" in vc, "routed empty state missing"
    assert "best-value-colleges-" in vc, "empty state should link the per-state best-value list"
    # Ranking, not just filtering: a scored sort must be present.
    assert "scored.sort" in vc
    # Accessibility + progressive load.
    assert 'role="combobox"' in vc and 'role="listbox"' in vc
    assert "aria-activedescendant" in vc
    # The old naive one-liner must be gone.
    assert 'SCHOOLS.filter(s => (s.name || "").toLowerCase().includes(term)).slice(0, 40)' not in vc
