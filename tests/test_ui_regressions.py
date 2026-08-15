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


def test_cip_plain_names_are_used_without_moving_urls():
    """Public-facing labels use human names; slugs still derive from the official CIP label so
    indexed URLs do not move; and the official label stays visible as provenance."""
    from pipeline.build_college_pages import slugify
    from pipeline.cip_names import PLAIN, has_plain_name, plain_name, short_label, tidy_official

    assert plain_name("5138", "Registered Nursing, Nursing Administration, ...") == "Nursing"
    assert plain_name("4201", "Psychology, General.") == "Psychology"
    # Unmapped fields fall back to the tidied official label, never to an invented one.
    assert plain_name("9999", "Some Unmapped Field.") == "Some Unmapped Field"
    assert plain_name(None, None) == ""
    # The trailing period in the federal file is stripped for display only.
    assert tidy_official("Biology, General.") == "Biology, General"
    assert has_plain_name("5138") and not has_plain_name("9999")

    # short_label trims a long enumerated label to its head term, but never mangles a short one
    # and never overrides a curated name.
    long_label = "Homeland Security, Law Enforcement, Firefighting and Related Protective Services"
    assert short_label("9998", long_label) == "Homeland Security"
    assert short_label("4201", "Psychology, General.") == "Psychology"
    assert short_label("9997", "Social Work.") == "Social Work"

    # URL stability: the slug must come from the OFFICIAL name, not the plain one.
    official = "Registered Nursing, Nursing Administration, Nursing Research and Clinical Nursing"
    assert slugify(official).startswith("registered-nursing")
    assert slugify(official) != slugify(plain_name("5138", official))

    # No curated name may be blank or accidentally identical to a bare CIP code.
    for code, nm in PLAIN.items():
        assert nm.strip(), f"empty plain name for {code}"
        assert not nm.strip().isdigit(), f"numeric plain name for {code}"


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


def test_homepage_has_brand_disambiguation_signals():
    """ "Truewise" collides with unrelated brands, so the homepage carries entity signals that tie
    the name to this specific product: an Organization + WebSite graph with the alternate name
    "Truewise US education data", a SearchAction, and og:site_name. All JSON-LD must be valid."""
    import json

    home = (SITE / "index.html").read_text()
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', home, re.S)
    assert blocks, "homepage has no JSON-LD"
    for b in blocks:
        json.loads(b)  # malformed structured data is worse than none
    assert '"@type": "Organization"' in home and '"@type": "WebSite"' in home
    assert '"alternateName": "Truewise US education data"' in home
    assert '"@type": "SearchAction"' in home
    # Consistent site name in every social share: homepage and the shared generated-page template.
    site_name = 'property="og:site_name" content="Truewise US education data"'
    assert site_name in home
    assert site_name in (PIPELINE / "build_college_pages.py").read_text()


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
    """The college search must not regress to a bare substring filter. The ranked matcher and
    alias map now live in the shared module; Value Check keeps the routed empty state + a11y."""
    mod = (SITE / "assets" / "college-search.js").read_text()
    assert "ALIASES" in mod, "alias map missing from shared module"
    assert "function searchSchools" in mod, "ranked search function missing from shared module"
    assert "scored.sort" in mod, "ranking (scored sort) missing from shared module"

    vc = (SITE / "value-check" / "index.html").read_text()
    assert "function detectState" in vc and "emptyStateHTML" in vc, "routed empty state missing"
    assert "best-value-colleges-" in vc, "empty state should link the per-state best-value list"
    # Accessibility + progressive load.
    assert 'role="combobox"' in vc and 'role="listbox"' in vc
    assert "aria-activedescendant" in vc
    # The old naive one-liner must be gone.
    assert 'SCHOOLS.filter(s => (s.name || "").toLowerCase().includes(term)).slice(0, 40)' not in vc


def test_all_college_pickers_share_one_search_module():
    """Value Check and Compare must both load the shared matcher, and neither may keep its own
    inline alias map, so a nickname like "UCLA" resolves identically in every picker (the audit
    caught Compare returning nothing for an alias the homepage advertised)."""
    for rel in ("value-check/index.html", "compare/index.html"):
        html = (SITE / rel).read_text()
        assert "/assets/college-search.js" in html, f"{rel} does not load the shared search module"
        assert "SEARCH_ALIASES = {" not in html, f"{rel} still defines an inline alias map"
        assert "ALIASES = {" not in html, f"{rel} still defines an inline alias map"


def test_compare_remove_control_is_an_accessible_button():
    """The Compare remove control was a click-only <div> (no keyboard, no name). It must be a
    real button with an accessible label, and the page must expose a polite live region."""
    html = (SITE / "compare" / "index.html").read_text()
    assert '<button type="button" class="rm"' in html, "remove must be a <button>"
    assert 'aria-label="Remove ' in html, "remove button needs an accessible name"
    assert '<div class="rm"' not in html, "the old inaccessible div.rm must be gone"
    assert 'aria-live="polite"' in html, "removals should be announced via a live region"


def test_home_and_hubs_have_self_canonical():
    """The homepage and hub pages had no canonical, so query-string and duplicate variants could
    split search equity. Each must self-reference; Value Check's canonical also collapses the
    dynamic ?school= URLs onto one indexable page."""
    expected = {
        "index.html": "https://truewise.dev/",
        "value-check/index.html": "https://truewise.dev/value-check/",
        "careers/index.html": "https://truewise.dev/careers/",
        "k12/index.html": "https://truewise.dev/k12/",
        "methodology/index.html": "https://truewise.dev/methodology/",
        "about/index.html": "https://truewise.dev/about/",
    }
    for rel, url in expected.items():
        html = (SITE / rel).read_text()
        assert f'<link rel="canonical" href="{url}" />' in html, (
            f"{rel} missing self-canonical {url}"
        )


def test_security_headers_present_and_csp_allows_site_resources():
    """A baseline security-header block must apply to every path, and the CSP must permit the
    resources the site actually loads (Google Fonts, the Cloudflare beacon) or it would break."""
    headers = (SITE / "_headers").read_text()
    for h in (
        "Strict-Transport-Security:",
        "X-Content-Type-Options: nosniff",
        "X-Frame-Options: DENY",
        "Referrer-Policy:",
        "Permissions-Policy:",
        "Content-Security-Policy:",
    ):
        assert h in headers, f"missing security header: {h}"
    csp = next(ln for ln in headers.splitlines() if "Content-Security-Policy:" in ln)
    for src in (
        "https://fonts.gstatic.com",
        "https://fonts.googleapis.com",
        "https://static.cloudflareinsights.com",
    ):
        assert src in csp, f"CSP would block a resource the site uses: {src}"
    assert "frame-ancestors 'none'" in csp
