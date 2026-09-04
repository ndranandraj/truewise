"""Guard the UI/UX fixes from 2026-08 so they cannot silently regress.

These are static checks on the shipped source (no data build needed), covering the three
highest-impact fixes: the .verdict class collision that broke ~5,254 pages, the responsive
table wrapper, the cache-control _headers file, and the search hardening.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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


def test_inner_pages_keep_a_mobile_gutter():
    """`.pg` sets `padding: 8px 0 64px`, which overrides the shared `.wrap` gutter and left the
    Majors and Lists content touching both viewport edges at 390px (2026-09-02 forest review).
    The shared head() must restore a horizontal gutter once the 860px box fills the viewport,
    matching the homepage: 40px down to 520px, then 20px."""
    head_css = (PIPELINE / "build_college_pages.py").read_text()
    assert "@media (max-width: 900px) {{ .pg {{ padding-left: var(--s8);" in head_css, (
        "inner pages must regain a horizontal gutter once the box fills the viewport"
    )
    assert "@media (max-width: 520px) {{ .pg {{ padding-left: var(--s5);" in head_css, (
        "inner pages must use the homepage 20px gutter on phones"
    )
    # And it must reach the shipped pages, on every generator that uses head(). Those trees are
    # gitignored and CI runs pytest without building the site, so only assert on what is present.
    for page in ("majors/index.html", "lists/index.html", "colleges/index.html"):
        built = SITE / page
        if not built.exists():
            continue
        assert "@media (max-width: 520px) { .pg { padding-left: var(--s5);" in built.read_text(), (
            f"{page} shipped without the mobile gutter"
        )


def _css_without_comments() -> str:
    """styles.css with /* ... */ stripped, so a rule's declarations can be parsed.

    These rules carry long explanatory comments, and a naive `padding:\\s*([^;]+);` happily matches
    prose inside one. Strip first, then read.
    """
    return re.sub(r"/\*.*?\*/", "", (SITE / "styles.css").read_text(), flags=re.S)


def test_inline_children_of_flex_columns_declare_align_self():
    """Flexbox BLOCKIFIES its children: `display: inline-block` on a flex item computes to `block`,
    and the default stretch then makes it fill the line.

    That shipped twice in one module. `.live-card .tag` rendered as a 350px dark band instead of a
    badge hugging "Start here", and `.live-cta` drew its underline across the whole column so it
    read as a rule rather than a link. Neither is visible in the source: the authored value and the
    computed value disagree. So any inline-block child of a flex column must say how it aligns.
    """
    css = _css_without_comments()
    flex_columns = set()
    for sel, body in re.findall(r"(\.[a-z0-9-]+)\s*\{([^}]*)\}", css):
        if "display: flex" in body and "flex-direction: column" in body:
            flex_columns.add(sel)
    assert ".live-card" in flex_columns, "expected .live-card to be a flex column"

    offenders = []
    for sel, body in re.findall(r"(\.[a-z0-9-][^{]*)\{([^}]*)\}", css):
        if "display: inline-block" not in body or "align-self" in body:
            continue
        # Only the ones actually parented by a known flex column.
        if any(c in sel for c in flex_columns):
            offenders.append(sel.strip())
    assert not offenders, (
        "inline-block inside a flex column without align-self; it will be blockified and "
        f"stretched: {offenders}"
    )


def test_module_dividers_do_not_outrun_their_content():
    """The columns are equal-height grid items, so bottom padding on a card left its 1px divider
    running past the last line as a stub with nothing beside it."""
    css = _css_without_comments()
    block = css.split(".live-card {", 1)[1].split("}", 1)[0]
    pad = re.search(r"padding:\s*([^;]+);", block)
    assert pad, ".live-card should set padding explicitly"
    parts = pad.group(1).split()
    assert len(parts) == 4 and parts[2] == "0", (
        f".live-card needs 0 bottom padding so the divider ends with the content, got {pad.group(1)!r}"
    )


def test_the_profile_strip_shares_a_baseline():
    """One item's description is a single line where its neighbours wrap to two. With
    align-items: center that dropped its heading 10px below the others."""
    css = _css_without_comments()
    block = css.split(".profile-strip {", 1)[1].split("}", 1)[0]
    assert "align-items: start" in block, (
        "the strip must top-align, or the shortest column's heading floats out of the row"
    )


def test_display_type_is_reserved_for_the_figure_not_the_sentence():
    """The finding band set its whole 17-word sentence at 76px mono: 13 lines, 988px, 73% of the
    band. The type roles reserve mono display sizing for FIGURES; the sentence around one is
    editorial prose. So the big treatment belongs on the <b>, and the paragraph itself must stay at
    a reading size."""
    css = _css_without_comments()
    para = css.split(".finding-stat {", 1)[1].split("}", 1)[0]
    figure = css.split(".finding-stat b {", 1)[1].split("}", 1)[0]
    assert "var(--t-lede)" in para, "the sentence must be set at a reading size, not a display size"
    assert "var(--display)" in para, "editorial prose uses the serif, per the type roles"
    assert "var(--mono)" in figure and "clamp(" in figure, (
        "the figure itself keeps the large mono treatment"
    )


def test_mobile_module_separators_are_horizontal():
    """The three homepage product modules are separated by vertical rules on desktop. Once they
    stack into one column the rule has to become horizontal, but `.live-card.flagship` (two
    classes) outranked the single-class mobile reset and kept its right-hand rule."""
    css = (SITE / "styles.css").read_text()
    assert ".live-card, .live-card.flagship { border-right: 0;" in css, (
        "the flagship module must drop its vertical rule when the modules stack"
    )


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
    """The deploy stamps BOTH styles.css and components.css with independent content hashes so a CSS
    change busts only its own cache. Guard relative+absolute refs, idempotency, no double-stamp, and
    that stamping one sheet never touches the other's version (the rebrand changes components.css)."""
    from pipeline import version_assets as va

    sver = va.sheet_hash("styles.css")
    assert re.fullmatch(r"[0-9a-f]{10}", sver), "styles hash should be 10 hex chars"
    cver = va.sheet_hash("components.css")
    assert cver is None or re.fullmatch(r"[0-9a-f]{10}", cver), "components hash 10 hex or absent"

    # Each sheet gets its OWN ?v=, on both relative and absolute refs.
    html = (
        '<link rel="stylesheet" href="styles.css" /><link href="/styles.css">'
        '<link rel="stylesheet" href="/components.css" />'
    )
    out = va.stamp_sheet(html, "styles.css", sver)
    out = va.stamp_sheet(out, "components.css", "deadbeef01")
    assert f'href="styles.css?v={sver}"' in out and f'href="/styles.css?v={sver}"' in out
    assert 'href="/components.css?v=deadbeef01"' in out

    # Idempotent, and a new hash replaces the old stamp rather than stacking.
    assert va.stamp_sheet(out, "styles.css", sver) == out
    assert va.stamp_sheet(out, "styles.css", "cafef00d99").count("styles.css?v=") == 2

    # Stamping components.css must not change the styles.css version, and vice versa.
    only_styles = va.stamp_sheet(html, "styles.css", sver)
    assert "components.css?v=" not in only_styles
    only_comp = va.stamp_sheet(html, "components.css", "deadbeef01")
    assert "styles.css?v=" not in only_comp

    # Back-compat helper still stamps the primary sheet.
    assert f'href="styles.css?v={sver}"' in va.stamp('<link href="styles.css">', sver)


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


def test_interactive_lists_are_keyboard_operable():
    """Careers rows and both compare-search result lists used click handlers on unfocusable <tr>/
    <li> elements, so keyboard and screen-reader users could not select them (audit TW-03). They
    must be real links/buttons, which are focusable and fire on Enter/Space natively."""
    careers = (SITE / "careers" / "index.html").read_text()
    assert 'a.mlink"' in careers or "a.mlink" in careers, "careers major name must be a link"
    assert 'tr.addEventListener("click"' not in careers, "no click handler on unfocusable rows"

    for rel, key in (("compare/index.html", "u"), ("k12/compare/index.html", "k")):
        html = (SITE / rel).read_text()
        assert f"button[data-{key}]" in html, f"{rel} results must be buttons"
        assert f"li[data-{key}]" not in html, f"{rel} must not attach clicks to bare <li>"
        assert 'li.addEventListener("click"' not in html, f"{rel} li click handler must be gone"


def test_k12_search_uses_the_provider_with_state_narrowing():
    """K-12 names repeat heavily (261 matches for "central high school"), so both K-12 searches use
    the shared provider and the courses page offers state narrowing rather than a long scroll."""
    for rel in ("k12/advanced-courses/index.html", "k12/compare/index.html"):
        html = (SITE / rel).read_text()
        assert "/assets/college-search.js" in html, f"{rel} must load the shared module"
        assert "K12SearchProvider" in html, f"{rel} must use the K-12 provider"
        assert 'INDEX.filter(s => (s.n || "").toLowerCase().includes(term))' not in html, (
            f"{rel} must not keep the old name-only substring filter"
        )
    courses = (SITE / "k12" / "advanced-courses" / "index.html").read_text()
    assert "statesFor" in courses and "statebar" in courses, "state narrowing missing"
    assert 'aria-live="polite"' in courses, "result count should be announced"


def test_k12_subnav_clears_the_sticky_header():
    """Both the site header and the K-12 subnav are sticky. Without an offset the subnav slides
    underneath the header while scrolling, so every K-12 page pins it below the 64px header."""
    for rel in (
        "k12/index.html",
        "k12/advanced-courses/index.html",
        "k12/compare/index.html",
        "k12/rankings/index.html",
    ):
        css = (SITE / rel).read_text()
        assert ".subnav {" in css and "top: 65px" in css, f"{rel} subnav must clear the header"


def test_compare_states_coverage_and_labels_are_honest():
    """A pass rate over 89 measured programs must not read like one over 254. Coverage is computed
    per school, and the completers column says what it actually counts."""
    compare = (SITE / "compare" / "index.html").read_text()
    assert "Programs measured" in compare, "coverage row missing from Compare"
    assert "n_insufficient" in compare, "coverage must include the unmeasured programs"
    # "Grads" implied the earnings-cohort sample size; it is a completions count.
    vc = (SITE / "value-check" / "index.html").read_text()
    assert "Recent completers" in vc and ">Grads<" not in vc
    gen = (PIPELINE / "build_college_pages.py").read_text()
    assert "Recent completers" in gen and '"num">Graduates<' not in gen


# Committed source pages (generated pages come from head(), checked separately). Not a glob,
# because stale generated output may sit in the working tree locally.
SOURCE_PAGES = [
    "404.html",
    "index.html",
    "about/index.html",
    "careers/index.html",
    "compare/index.html",
    "methodology/index.html",
    "value-check/index.html",
    "k12/index.html",
    "k12/advanced-courses/index.html",
    "k12/compare/index.html",
    "k12/rankings/index.html",
]

# The only three faces the stylesheet asks for. See site/fonts/README.md.
FONT_FILES = [
    "source-serif-4-latin-400-normal.woff2",
    "source-serif-4-latin-600-normal.woff2",
    "ibm-plex-mono-latin-500-normal.woff2",
]


def test_fonts_are_self_hosted_with_no_third_party_origin():
    """Release 3 B3 replaced Google Fonts with self-hosted faces. The Google origins put a
    third-party connection (two preconnects, a stylesheet round trip, then the files) on the
    critical path of every page, so no page may reach for them again, and Libre Franklin is gone."""
    for rel in FONT_FILES:
        f = SITE / "fonts" / rel
        assert f.exists(), f"missing self-hosted face: {rel}"
        assert f.read_bytes()[:4] == b"wOF2", f"{rel} is not a valid woff2 file"
    css = (SITE / "styles.css").read_text()
    # A render-blocking @import was the 2026-08-25 perf regression; it must never come back.
    assert "@import url" not in css, "styles.css must not @import fonts (render-blocking)"
    for rel in FONT_FILES:
        assert f'url("/fonts/{rel}")' in css, f"styles.css has no @font-face for {rel}"
    assert css.count("font-display: swap;") == len(FONT_FILES), (
        "every @font-face needs font-display: swap so text stays visible while a face loads"
    )
    pages = [(rel, (SITE / rel).read_text()) for rel in SOURCE_PAGES]
    pages.append(("build_college_pages.head()", (PIPELINE / "build_college_pages.py").read_text()))
    pages.append(("embed/index.html", (SITE / "embed" / "index.html").read_text()))
    for name, text in pages:
        for gone in ("fonts.googleapis.com", "fonts.gstatic.com", "Libre Franklin"):
            assert gone not in text, f"{name} still references {gone}"
    # Sweep whatever generated output is present too. Those directories are gitignored, so this is
    # a no-op in CI, but locally it catches pages a generator has not rewritten since the change:
    # /findings/ and /updates/ were still shipping a render-blocking font stylesheet from before the
    # 2026-08-25 perf fix precisely because no test looked at generated output.
    stale = [
        str(p.relative_to(SITE))
        for p in SITE.rglob("*.html")
        if "fonts.googleapis.com" in p.read_text() or "fonts.gstatic.com" in p.read_text()
    ]
    assert not stale, f"generated pages still reference Google Fonts: {stale[:5]}"


def test_every_page_preloads_exactly_the_faces_it_renders():
    """Fonts are only discovered after the stylesheet parses, so each page preloads its faces to
    keep them off the critical path. Preloading a face a page never renders wastes the download
    and logs a "preloaded but not used" console warning, so the set must match what the page uses:
    the 600 display and 500 mono render everywhere (brand and footer), while the 400 display is
    only reached through .lede and .prose."""
    always = ["source-serif-4-latin-600-normal.woff2", "ibm-plex-mono-latin-500-normal.woff2"]
    only_if_used = "source-serif-4-latin-400-normal.woff2"
    pages = [(rel, (SITE / rel).read_text()) for rel in SOURCE_PAGES]
    # The generated-page shell renders no .lede/.prose, so it must preload the two faces only.
    pages.append(("build_college_pages.head()", (PIPELINE / "build_college_pages.py").read_text()))
    for name, text in pages:
        for face in always:
            assert f'rel="preload" href="/fonts/{face}"' in text, f"{name} does not preload {face}"
        # Fonts are fetched in CORS mode even same-origin: without crossorigin the preload is not
        # reused and the browser downloads the file twice.
        assert 'as="font" type="font/woff2" crossorigin' in text, (
            f"{name} font preload is missing crossorigin, so it would be fetched twice"
        )
        uses_400 = 'class="lede"' in text or 'class="prose"' in text
        preloads_400 = f'rel="preload" href="/fonts/{only_if_used}"' in text
        assert preloads_400 == uses_400, (
            f"{name} preloads the 400 display face={preloads_400} but renders it={uses_400}"
        )


def test_no_orphaned_pages_would_ship():
    """`wrangler deploy` uploads everything under site/, and build_sitemap scans the DISK, so a
    pre-rendered page the current build no longer produces would both ship and enter the sitemap.
    Deploy builds from a clean checkout, so this only bites locally: on 2026-09-02 a preview served
    thirteen stale pages that production correctly 404s, twelve college slugs
    (/college/university-of-st-thomas-mn/ and eleven others) plus /findings/data-audit/.
    Guards /college/ and /findings/, the two trees with a published authority to diff against.
    Both are gitignored, so this is a no-op in CI."""
    college = SITE / "college"
    slug_map = college / "slug-map.json"
    if not slug_map.exists():
        pytest.skip("no built college tree in this working copy")
    from pipeline.prune_orphans import find_orphans

    orphans = find_orphans()
    assert not orphans, (
        f"{len(orphans)} orphaned page(s) would ship: {orphans[:5]}. "
        "Run `make prune` to delete them."
    )


def test_fonts_are_cached_immutably():
    """Font filenames pin family, weight and subset, so the bytes at a URL never change and the
    files can be held for a year. Without this they would inherit the platform default of
    revalidating on every navigation, which defeats self-hosting."""
    headers = (SITE / "_headers").read_text()
    assert "/fonts/*" in headers, "_headers has no cache rule for the self-hosted fonts"
    block = headers.split("/fonts/*", 1)[1]
    assert "immutable" in block.split("\n\n", 1)[0], "/fonts/* should be immutable"


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
    # Two providers behind one contract (Stage 0.2): colleges rank on name/alias/city/state/size,
    # K-12 on name with state and district as filters. One matcher for both makes each worse.
    assert "CollegeSearchProvider" in mod and "K12SearchProvider" in mod
    assert "searchSchools" in mod, "back-compat shim for the shipped pages must remain"
    assert "out.sort" in mod, "ranking (scored sort) missing from shared module"
    assert "editDistance" in mod, "typo tolerance missing"

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
    resources the site actually loads (the Cloudflare beacon) or it would break. Since B3 the
    fonts are self-hosted, so the font origins must be GONE from the CSP rather than allowed."""
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
    assert "https://static.cloudflareinsights.com" in csp, (
        "CSP would block a resource the site uses: the Cloudflare beacon"
    )
    # Self-hosted fonts: 'self' must cover them and the Google origins must not be re-granted.
    assert "font-src 'self';" in csp, "font-src must allow the self-hosted /fonts files"
    for gone in ("https://fonts.gstatic.com", "https://fonts.googleapis.com"):
        assert gone not in csp, f"CSP still grants a font origin the site no longer uses: {gone}"
    # Frame protection is X-Frame-Options, NOT a CSP frame-ancestors directive: Cloudflare appends
    # (does not replace) a per-path CSP, so a global frame-ancestors 'none' could not be relaxed on
    # /embed/. X-Frame-Options can be unset per-path with `!`, so the embed widget can opt out.
    assert "frame-ancestors" not in csp, "global CSP must not set frame-ancestors (see /embed/)"
    embed = headers.split("/embed/*", 1)
    assert len(embed) == 2, "missing /embed/* rule"
    assert "! X-Frame-Options" in embed[1], (
        "/embed/ must unset X-Frame-Options so it can be iframed"
    )
