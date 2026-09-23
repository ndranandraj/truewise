"""Guard the UI/UX fixes from 2026-08 so they cannot silently regress.

These are static checks on the shipped source (no data build needed), covering the three
highest-impact fixes: the .verdict class collision that broke ~5,254 pages, the responsive
table wrapper, the cache-control _headers file, and the search hardening.
"""

from __future__ import annotations

import json
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
    """Inner pages must keep the shared .wrap gutter (40px, then 20px on phones).

    `.pg` once set `padding: 8px 0 64px`, which zeroed the .wrap gutter and left Majors and Lists
    touching both viewport edges at 390px (2026-09-02 forest review). The page shell now leaves the
    horizontal padding to .wrap entirely, so the guard is that nothing zeroes it again.
    """
    head_css = (PIPELINE / "build_college_pages.py").read_text()
    shell = re.search(r"\.pg \{\{([^}]*)\}\}", head_css)
    assert shell, "head() should still style .pg"
    assert "padding:" not in shell.group(1), "use padding-top/bottom so the .wrap gutter survives"
    assert not re.search(r"\.pg \{\{[^}]*padding:\s*\S+\s+0", head_css), (
        ".pg must not zero the horizontal gutter"
    )


def test_every_page_title_starts_where_the_logo_starts():
    """One shell: main keeps the .wrap container and narrow columns sit against its left edge.

    Profiles, majors, lists and findings centred an 860px box, Methodology a 760px one, and the
    app pages used the full 1240px container. At 1280px the page title started at 210px, 260px or
    60px depending on the page. Capping the column on main itself (with .wrap's auto margins)
    is what centres it, so the cap belongs on the children.
    """
    sources = {
        "build_college_pages.py": (PIPELINE / "build_college_pages.py").read_text(),
        "methodology": (SITE / "methodology" / "index.html").read_text(),
        "about": (SITE / "about" / "index.html").read_text(),
    }
    for name, text in sources.items():
        css = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for cls in ("pg", "doc"):
            rule = re.search(r"\." + cls + r" \{+([^}]*)\}", css)
            if rule:
                assert "max-width" not in rule.group(1), (
                    f"{name}: .{cls} caps main itself, which centres the column off the shared edge"
                )
            # The column cap must carry zero specificity. Written as `.pg > *` it tied with, and
            # being later overrode, every child's own narrower measure: the source notes on 6,127
            # profiles widened from about 66ch to the full 860px in the first preview.
            assert not re.search(r"(?<!\()\." + cls + r" > \*", css), (
                f"{name}: cap .{cls} children with :where(.{cls}) > * so child measures still win"
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


def test_type_is_a_generated_token_layer():
    """The root cause of the ad-hoc type on the generated pages.

    design/tokens.json had color, semantic, chart, scale and font blocks but NO type block, so the
    steps lived in a second hand-written :root that build_tokens never saw. The pipeline could
    guarantee colour consistency structurally and could not guarantee type at all: `make
    tokens-check` had nothing to compare, and head() had no token to reach for, which is how 13
    ad-hoc rem sizes and a 115ch measure became the only option available.

    Type is now generated like colour. The five original steps must keep their exact values, or
    every page that already uses them shifts.
    """
    tokens = json.loads((ROOT / "design" / "tokens.json").read_text())
    assert "type" in tokens, "tokens.json needs a type block, or type cannot be guaranteed"
    for name, value in {
        "t-label": "12px",
        "t-fine": "13px",
        "t-ui": "15px",
        "t-sub": "18px",
        "t-lede": "20px",
    }.items():
        assert tokens["type"][name] == value, f"{name} changed value; existing pages would shift"
    # Eight steps and two measures, named as the Release 3 review section 02 names them. The names
    # are asserted, not just their presence: a second vocabulary for the same scale is the whole
    # failure this block exists to end, and t-section in particular is the rung whose absence left
    # a 44px page title sitting straight on a 15px label.
    steps = [n for n in tokens["type"] if n.startswith("t-")]
    assert steps == [
        "t-label",
        "t-fine",
        "t-ui",
        "t-sub",
        "t-lede",
        "t-section",
        "t-title",
        "t-display",
    ], f"the type scale is not the reviewed one: {steps}"
    # Measures, whose absence let prose inherit the 860px table frame at ~115 characters a line.
    for name in ("measure", "measure-tight"):
        assert tokens["type"][name].endswith("ch"), f"{name} must be in ch, it constrains prose"

    css = (SITE / "styles.css").read_text()
    generated = css.split("@tokens:start", 1)[1].split("@tokens:end", 1)[0]
    for name in tokens["type"]:
        if not name.startswith("$"):
            assert f"--{name}:" in generated, f"--{name} is not in the generated block"
    # And nothing may redeclare them by hand outside it, which is what drifted before.
    outside = css.split("@tokens:end", 1)[1]
    handwritten = re.findall(r"^\s*--(t-[a-z]+|measure[a-z-]*)\s*:", outside, re.M)
    assert not handwritten, (
        f"type tokens re-declared by hand outside the generated block: {handwritten}"
    )


def test_every_scrollable_table_shows_that_it_scrolls():
    """A table whose columns run off the right edge with no cue hides data rather than deferring it.

    Eleven wrappers carried `overflow-x: auto` and nothing else. Because there are only three
    wrapper class names site-wide, one rule in styles.css covers all of them; this test fails if a
    fourth name appears, since a new name would silently opt out of the cue.
    """
    css = _css_without_comments()
    cue = re.search(r"\.tscroll, \.table-wrap, \.tw-table__scroll \{([^}]*)\}", css)
    assert cue, "the shared scroll-cue rule is missing from styles.css"
    body = cue.group(1)
    assert "local" in body and "scroll" in body, (
        "the cue needs both the content-pinned covers and the box-pinned shadows, "
        "or it shows a shadow when there is nothing left to scroll to"
    )

    known = {".tscroll", ".table-wrap", ".tw-table__scroll"}
    found = set()
    sources = list(SITE.glob("*.html")) + list(SITE.glob("*/index.html"))
    sources += [SITE / "styles.css", ROOT / "components" / "components.css"]
    sources += [PIPELINE / "build_college_pages.py"]
    for path in sources:
        if not path.exists():
            continue
        text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
        for sel in re.findall(
            r"(\.[a-z][\w-]*(?:__[\w-]+)?)\s*\{\{?[^{}]*overflow-x:\s*auto", text
        ):
            found.add(sel)
    assert found <= known, f"scroll wrappers with no cue: {sorted(found - known)}"


def test_every_scroll_region_can_be_reached_by_keyboard():
    """A cue tells a sighted user the region scrolls. It does nothing for a keyboard user.

    An overflow container is not focusable by default. Chrome and Firefox now focus scrollers
    natively, but Safari does not, so there the off-screen columns of every one of these tables
    were unreachable without a pointer: WCAG 2.1.1. Each wrapper carries tabindex="0" plus a role
    and an accessible name, written into the markup rather than added by script so it holds with
    JavaScript off.

    Every emission site is checked, not a sample: one wrapper left plain is one table a keyboard
    user cannot read to the end.
    """
    sources = [
        PIPELINE / "build_canonical_profiles.py",
        PIPELINE / "build_college_pages.py",
        PIPELINE / "build_lists.py",
        PIPELINE / "build_majors_pages.py",
        PIPELINE / "build_stats_exposure.py",
        PIPELINE / "build_profile_pilot.py",
        ROOT / "components" / "table.js",
        SITE / "careers" / "index.html",
        SITE / "compare" / "index.html",
        SITE / "value-check" / "index.html",
        SITE / "k12" / "compare" / "index.html",
    ]
    opening = re.compile(r'<div class="(?:tscroll|table-wrap|tw-table__scroll)"[^>]*>')
    plain = []
    for path in sources:
        if not path.exists():
            continue
        for tag in opening.findall(path.read_text()):
            if 'tabindex="0"' not in tag or "aria-label=" not in tag:
                plain.append(f"{path.name}: {tag}")
    assert not plain, "scroll regions a keyboard user cannot enter:\n" + "\n".join(plain)


def test_compare_does_not_clip_a_single_school():
    """`table.cmp { min-width: 560px }` forced a horizontal scroll even with one school added,
    whose sticky label column plus one school column comes to roughly 292px and fits a 390px phone
    outright. The floor belongs on the school column, so one school fits and two or more scroll
    because they genuinely need to."""
    html = (SITE / "compare" / "index.html").read_text()
    table = re.search(r"table\.cmp \{([^}]*)\}", html)
    assert table, "table.cmp rule not found"
    assert "min-width" not in table.group(1), (
        "a table-level min-width clips the one-school case regardless of how little it contains"
    )
    assert re.search(r"table\.cmp thead th:not\(:first-child\)[^{]*\{[^}]*min-width", html), (
        "the width floor should sit on the school column instead"
    )


def test_the_colleges_module_states_its_selection_rule():
    """The contract's editorial governance: any module surfacing a subset of colleges must state
    its rule in words on the page, apply it deterministically, and never accept placement.

    This one matters more than the rule itself. Ordering by completions surfaces Chamberlain,
    Western Governors, Grand Canyon, Walden and Capella for nursing, all large online
    institutions. Unlabelled, that list reads as an endorsement by the site that exists to
    scrutinise them. Labelled "where the most students complete", it is simply true.

    A "best colleges for X" module would be a ranking this data cannot support, so the page says
    what the order means and what it does not.
    """
    src = (PIPELINE / "build_majors_pages.py").read_text()
    assert "not a judgement about where to" in src, (
        "the page must disclaim the ranking reading, or the order implies a recommendation"
    )
    assert "the most students complete" in src, "the rule must be stated in words, not implied"
    assert "that report one" in src, (
        "the subset must be shown against the whole, or eight colleges read as all of them"
    )
    # Deterministic: completions then unitid, so a tie cannot move a link between builds.
    assert "ORDER BY cip4, completions DESC, unitid" in src, (
        "ordering on completions alone leaves ties to the query planner"
    )
    # And no college is linked without a profile to land on.
    assert "if u in slugs" in src, "link only where a profile page actually exists"


def test_a_programme_links_to_its_major_by_cip_not_by_name():
    """The join is the 4-digit CIP, because a major page IS a 4-digit CIP.

    Matching on the programme name would be approximate, and the contract says exact relationships
    only. A field with no major page, 137 of 429 fall below the ranking threshold, gets no link
    rather than a guessed one.

    Both renderers build the link from the same `major` field on the row, so enhancement cannot
    move a link: the static core and the JS component must agree on where a row points.
    """
    py = (PIPELINE / "build_profile_pilot.py").read_text()
    assert "def major_slug_for(" in py, "the CIP to major mapping needs one entry point"
    assert "str(cip_code)[:4]" in py, "the join must be on the 4-digit CIP"
    assert '"major": major_slug_for(r["cip_code"])' in py, (
        "the row shape must carry the slug, or each renderer resolves it separately"
    )
    assert 'href="/majors/{_esc(slug)}/"' in py, "the static row must render a real anchor"

    js = (ROOT / "components" / "table.js").read_text()
    assert 'href="/majors/${esc(r.major)}/"' in js, (
        "the component must render the same link from the same field"
    )


def test_the_row_builder_does_not_need_the_warehouse():
    """CI runs pytest WITHOUT building the site or the data.

    The CIP to major map is derived from value_check.parquet, which is data rather than source and
    is gitignored, so a row builder that needed the warehouse to construct a row would fail every
    test that touches one. It did, on the first attempt, and the CI simulation caught it before the
    push rather than after.

    The condition is the parquet's presence, not a bare except, so a real build with the data
    present still surfaces any error in building the map instead of silently dropping 195,305
    links.
    """
    src = (PIPELINE / "build_profile_pilot.py").read_text()
    assert 'if not (PARQUET_DIR / "value_check.parquet").exists():' in src, (
        "the map must be conditional on the data existing"
    )
    body = src.split("def major_slug_for", 1)[1]
    body = body[: body.index("\ndef ")]  # up to the next top-level function
    # Check the CONSTRUCT, not the word: the comment inside this function contains "except" as
    # prose, and matching that is the same mistake as a regex hitting `font-display: swap` inside
    # a comment about font-display: swap. It has happened three times on this project.
    assert "try:" not in body, (
        "swallowing the error would hide a genuine failure to build the map in a real build"
    )


def test_major_slugs_cannot_become_order_dependent():
    """Profile pages now link at major slugs, so those slugs are a URL contract.

    The slug is a pure function of the name today, because no two major names slugify alike. The
    collision branch is what would make it depend on iteration order, which is exactly how the
    college slugs became unstable across processes and had to be frozen into a registry. This
    fails the day a collision appears, while it is still a build error rather than 6,127 profiles
    pointing somewhere new.
    """
    src = (PIPELINE / "build_majors_pages.py").read_text()
    assert "def major_slugs(" in src, "one function must own the CIP to slug map"
    # The sort key includes the CIP, so even a future name tie orders deterministically.
    assert 'key=lambda kv: (kv[1]["name"].lower(), kv[0])' in src, (
        "sorting on the name alone leaves ties to iteration order, the college-slug bug again"
    )


def test_money_signs_negatives_outside_the_symbol():
    """ "$-2,533" is what naive formatting produces and it reads as a bug rather than a number.

    It was on 38 profiles. A College Scorecard net price genuinely goes negative when grant aid
    exceeds the published cost of attendance, MIT's lowest income band among them, so the figure is
    real and stays. It is written "-$2,533" now, and where any band is negative the table says what
    a negative net price means, because otherwise a reader discounts the whole table.

    Five separate money() implementations existed, one per surface. All five are fixed; a sixth
    would reintroduce the bug on whichever page it served.
    """
    py = (PIPELINE / "build_college_pages.py").read_text()
    assert 'f"-${abs(v):,}"' in py, "the Python formatter must sign outside the symbol"
    js_files = [
        ROOT / "components" / "table.js",
        SITE / "careers" / "index.html",
        SITE / "compare" / "index.html",
        SITE / "embed" / "index.html",
        SITE / "value-check" / "index.html",
    ]
    for path in js_files:
        src = path.read_text()
        for m in re.finditer(r"const money = [^;]+;", src, re.S):
            assert '"-$"' in m.group(0), f"{path.name} formats a negative as $-n"

    profiles = (PIPELINE / "build_canonical_profiles.py").read_text()
    assert "A negative net price means grant aid exceeded" in profiles, (
        "a negative net price needs explaining where it appears, or it reads as an error"
    )


def test_a_non_state_code_is_never_rendered_as_a_place():
    """461 live pages said "a typical ZZ high-school graduate".

    ZZ is not a state. Those 461 schools have no city and no state earnings benchmark either, so it
    is the source data's "not reported" bucket, and rendering it as a place is the same failure as
    showing a suppressed value as 0. The honesty rules forbid it: unknown is labelled unknown.

    Neither the design review nor the growth audit caught this. It surfaced only because putting the
    state into the title made it visible in a second place.

    The /colleges/zz/ URL is unchanged, because published routes are a frozen contract. Only what a
    reader sees changes.
    """
    src = (PIPELINE / "build_college_pages.py").read_text()
    assert "def state_label(" in src and "def known_state(" in src, (
        "one function must decide what an unrecognised code is called, or prose, titles, "
        "breadcrumbs and the hub drift apart again"
    )
    # The raw fallback is what produced "ZZ": STATE_NAMES.get(st, st) hands back the code itself.
    for path in (PIPELINE / "build_college_pages.py", PIPELINE / "build_canonical_profiles.py"):
        assert "STATE_NAMES.get(st, st)" not in path.read_text(), (
            f"{path.name} falls back to the raw code, which prints ZZ as if it were a place"
        )

    # And it must not have reached the built pages.
    built = list(SITE.glob("college/*/index.html"))
    if built:
        leaked = [p.name for p in built[:400] if "ZZ high-school graduate" in p.read_text()]
        assert not leaked, f"{len(leaked)} built profiles still name ZZ as a state"


def test_college_titles_carry_the_place():
    """86 title values were shared by 202 pages, Cortiva Institute six times, so those pages
    competed with each other for one result. The September baseline also showed the query shape
    they were losing: "miller motte in fayetteville nc" at position 54.9 and "southern careers waco"
    at 78.2, both name-plus-city, against titles carrying no city at all.

    The suffix shortens in the same change, so the median title did not grow.
    """
    src = (PIPELINE / "build_canonical_profiles.py").read_text()
    assert "{name}, {where}: cost and graduate earnings" in src, "title must carry the place"
    assert "what families pay and what graduates earn" not in src, (
        "the 41-character suffix should be gone from the profile title"
    )
    # A school with no location gets no invented one.
    assert "{name}: cost and graduate earnings" in src, (
        "an unlocated school must fall back to the bare name rather than an invented place"
    )


def test_long_lists_open_at_a_page_and_state_the_whole():
    """The audit's central design finding, on both surfaces that had it.

    A Penn State profile rendered 150 stacked rows about 47,000px tall on a phone and Careers
    rendered 400 in a page about 36,100px. Neither is an interface: the search and filters that
    would have narrowed them sat above a wall of rows nobody scrolled back up from.

    Two rules make a reveal limit honest rather than a way of hiding data. The count must be stated
    against the whole set, so "Showing 20 of 489" and never "20 programs". And the default filters
    must all be empty, so the opening view is the complete list in miniature, including the
    suppressed rows, rather than a flattering subset.
    """
    js = (ROOT / "components" / "table.js").read_text()
    assert re.search(r"const PAGE = \d+", js), "the program table needs a reveal page size"
    assert "this.shown = PAGE" in js, "it must open at one page rather than at everything"
    for empty in ('this.query = ""', 'this.verdict = ""', 'this.credential = ""'):
        assert empty in js, f"filters must start empty, or the opening view is a subset: {empty}"
    # The count reports against loaded rows PLUS the unfetched tail, not the visible slice.
    assert "const total = loaded + this.remaining" in js, (
        "the count must include the programs not yet fetched, or it understates the school"
    )

    careers = (SITE / "careers" / "index.html").read_text()
    assert "rows.slice(0, shown)" in careers, "Careers should reveal a page, not its first 400"
    assert "Showing ${visible.toLocaleString()} of ${rows.length.toLocaleString()}" in careers, (
        "Careers must state the visible count against the whole set"
    )
    assert "shown = PAGE; draw();" in careers, (
        "changing the search or a filter must reset the reveal, or a narrowed set opens part-way "
        "down the previous, wider one"
    )


def test_the_compare_swap_matches_what_the_table_needs_at_capacity():
    """The breakpoint is arithmetic, not a device size.

    At 768px with four schools the table came back and scrolled, leaving 33px of a 142px metric
    label at the right edge, which fails "row labels stay understandable". Picking a bigger round
    number would have been a guess. The table needs its metric column plus MAX schools at their
    minimum column width plus both page gutters, and the swap is set to exactly that, so the same
    page never scrolls or not depending on how many schools someone happened to add.

    This recomputes the sum from the declared values, so changing any one of them without moving
    the breakpoint fails here rather than on someone's tablet.
    """
    html = (SITE / "compare" / "index.html").read_text()
    css = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    label = int(re.search(r"table\.cmp tbody th \{[^}]*width: (\d+)px", css).group(1))
    school = int(
        re.search(
            r"table\.cmp thead th:not\(:first-child\)[^{]*\{[^}]*min-width: (\d+)px", css
        ).group(1)
    )
    most = int(re.search(r"MAX\s*=\s*(\d+)", html).group(1))
    gutter = 40  # .wrap padding, both sides
    needed = label + most * school + 2 * gutter
    swap = int(re.search(r"@media \(max-width: (\d+)px\)", css).group(1))
    assert swap + 1 >= needed, (
        f"the table appears from {swap + 1}px but needs {needed}px to hold {most} schools "
        f"({label}px label + {most} x {school}px + {2 * gutter}px gutters), so it will scroll "
        "its metric labels out of view"
    )


def test_the_compare_cards_cannot_squeeze_out_a_school_name():
    """A grid column of `auto` sizes to its own content, so the longest helper text on a card set
    the value column to 233px and left the school name 35px at 320px and 90px at 390px, wrapping
    names into near-vertical fragments. Both columns must be fractions, which cap each side
    whatever the value happens to say."""
    css = re.sub(r"/\*.*?\*/", "", (SITE / "compare" / "index.html").read_text(), flags=re.S)
    rule = re.search(r"\.cmp-metric dl > div \{([^}]*)\}", css)
    assert rule, ".cmp-metric row rule not found"
    cols = re.search(r"grid-template-columns:\s*([^;]+);", rule.group(1))
    assert cols, "the card row needs explicit columns"
    assert "auto" not in cols.group(1), (
        f"an auto column lets one long value starve the school name: {cols.group(1)!r}"
    )
    assert cols.group(1).count("fr") == 2, f"both columns should be fractions: {cols.group(1)!r}"


def test_long_programme_names_cannot_set_the_page_width():
    """CIP names run slashes together without spaces, and browsers do not break on "/".

    "Agricultural/Animal/Plant/Veterinary" is 36 unbroken characters; at the 18px mobile programme
    size that is roughly 324px of min-content width, which pushed a Penn State phone page to 354px
    inside a 320px viewport and produced a document-level horizontal scrollbar. Two names on one
    page were enough.

    `overflow-wrap: anywhere` rather than `break-word`, because only `anywhere` also lowers the
    intrinsic minimum, and the intrinsic minimum is the measurement doing the damage.
    """
    css = (ROOT / "components" / "components.css").read_text()
    rule = re.search(r"\n\.tw-td--program \{([^}]*)\}", css)
    assert rule, ".tw-td--program rule not found"
    assert "overflow-wrap: anywhere" in rule.group(1), (
        "break-word would still let the unbroken run set the min-content width"
    )
    mobile = re.search(r"@media \(max-width: 768px\) \{(.*?)\n\}", css, re.S)
    assert mobile and re.search(r"\.tw-td--program \{[^}]*min-width: 0", mobile.group(1)), (
        "the programme cell is a flex item on mobile and will not shrink below its content "
        "without min-width: 0"
    )


def test_compare_has_no_horizontal_axis_on_a_phone():
    """The sticky-label table was the interim repair and it failed its own acceptance criteria.

    At 320px one school still overflowed the 280px content box, and with two or more schools a
    fragment of the outgoing column sat between the sticky label and the next full column, so a
    phone user read partial words and partial values. The contract's fallback clause says that is
    the point to stop refining the table, so below the swap width it is replaced outright by
    metric-major cards: one card per measure, each school listed under it.

    The swap was 700px when the cards were first written, a round number chosen by eye, and it is
    929px now. The test above derives that figure from the table's own declarations rather than
    restating it, which is why this docstring should not name a width at all.

    Grouping by metric rather than by school is deliberate. Stacking one school per card would put
    the two figures being compared a scroll apart, which is the one thing Compare exists to avoid.
    """
    html = (SITE / "compare" / "index.html").read_text()
    css = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    # The exact width is owned by the arithmetic test above; here only the swap itself matters.
    swap = re.search(r"@media \(max-width: \d+px\) \{(.*?)\n    \}", css, re.S)
    assert swap, "no breakpoint that swaps the table for the cards"
    assert ".table-wrap { display: none; }" in swap.group(1), "the table must be gone, not shrunk"
    assert ".cmp-stack { display: block; }" in swap.group(1), "the cards must take its place"
    # Exactly one of the two is displayed at any width, so the duplicate Remove buttons never both
    # sit in the tab order. Same reasoning as the mobile sort control.
    assert ".cmp-stack { display: none;" in css, "the cards must be hidden above the breakpoint"
    # And the table keeps no phone-only scaffolding it no longer needs.
    assert "position: sticky" not in css, (
        "the sticky metric column was scaffolding for a scroll that no longer happens"
    )
    assert 'class="cmp-stack"' in html, "the renderer must emit the phone view"


def test_every_public_hand_written_page_declares_a_canonical():
    """/k12/rankings/, /k12/compare/ and /k12/advanced-courses/ shipped with titles and
    descriptions but no canonical, while /k12/ had one. K-12 is a distinct content family, so a
    gap there costs clean indexing signals on exactly the routes that need them.

    404 is excluded: it is noindex by design and a canonical on an error page is wrong.
    """
    missing = []
    for path in sorted(SITE.rglob("index.html")):
        if any(part in str(path) for part in ("/college/", "/majors/", "/lists/", "/embed/")):
            continue
        html = path.read_text()
        if "noindex" in html:
            continue
        route = "/" + str(path.parent.relative_to(SITE)).replace(".", "").strip("/")
        route = "/" if route == "/" else route.rstrip("/") + "/"
        found = re.search(r'rel="canonical" href="([^"]+)"', html)
        if not found:
            missing.append(f"{route} has no canonical")
        elif found.group(1) != f"https://truewise.dev{route}":
            missing.append(f"{route} canonical points at {found.group(1)}")
    assert not missing, "canonical problems:\n" + "\n".join(missing)


def test_every_form_control_has_a_real_label():
    """Careers scored 93 on Lighthouse accessibility for exactly one reason: its field and sort
    selects had no <label> and no accessible name, so a screen-reader user heard "combo box" twice
    with nothing to distinguish them. Three search inputs had the same problem in a quieter form,
    relying on a placeholder, which is not a label: it is not reliably announced, it disappears the
    moment someone types, and the long ones truncated mid-sentence at 320px.

    Every control on a hand-written page needs a <label for> or an aria-label. Generated pages are
    covered by the component smokes, which assert the same thing on the rendered output.
    """
    control = re.compile(r"<(select|input|textarea)\b([^>]*)>")
    unlabelled = []
    for path in sorted(SITE.rglob("*.html")):
        if any(part in str(path) for part in ("/college/", "/majors/", "/lists/", "/findings/")):
            continue
        html = path.read_text()
        labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
        for tag, attrs in control.findall(html):
            if re.search(r'type="(hidden|submit|button)"', attrs) or "aria-label" in attrs:
                continue
            ident = re.search(r'id="([^"]+)"', attrs)
            if ident and ident.group(1) in labelled:
                continue
            unlabelled.append(f"{path.relative_to(SITE)}: <{tag}{attrs[:60]}>")
    assert not unlabelled, "controls with no label and no accessible name:\n" + "\n".join(
        unlabelled
    )


def test_nothing_focusable_is_hidden_by_the_clip_pattern():
    """A phone-width keyboard trap that no screenshot could show.

    The mobile program table hid its header row with the 1px-clip pattern (position:absolute,
    width:1px, clip:rect(0 0 0 0)). That pattern hides content visually while KEEPING it in the
    accessibility tree and the tab order, which is exactly right for a label a screen-reader user
    still needs, and exactly wrong here: the header row contains six sort <button>s, so a keyboard
    user on a phone tabbed through six controls that were not on screen, on every profile page.

    thead is display:none now, each cell carries its own column name through data-label, and
    sorting moved to the visible .tw-sort control. This fails if thead goes back to being clipped.
    """
    css = (ROOT / "components" / "components.css").read_text()
    thead = re.search(r"\.tw-table thead \{([^}]*)\}", css)
    assert thead, ".tw-table thead rule not found"
    body = thead.group(1)
    assert "display: none" in body, "thead must be removed, not clipped: it holds the sort buttons"
    assert "clip:" not in body, "the clip pattern keeps the sort buttons focusable while invisible"

    # And the replacement must be a real, visible control rather than another hidden one.
    sort = re.search(r"\n\.tw-sort \{([^}]*)\}", css)
    assert sort, ".tw-sort rule not found"
    assert "clip:" not in sort.group(1), "the mobile sort control must not be visually hidden"
    js = (ROOT / "components" / "table.js").read_text()
    assert 'class="tw-sort__select"' in js, "table.js must render the visible mobile sort control"


def test_no_generator_or_stylesheet_invents_a_type_size():
    """The other half of the same root cause.

    A type block in tokens.json only helps if the renderers actually reach for it. Before this,
    head() in build_college_pages.py carried 13 distinct ad-hoc rem sizes and components.css
    carried another 12, which is how a profile page ended up with a 40px title sitting straight on
    a 19.2px heading while the homepage was on a clean scale. Every size in both is now a --t-*
    token, and this test fails if a new rem or px size appears in either.

    Four sizes are deliberately not tokens and are named here so the exemption is explicit rather
    than a hole: the text inputs and selects (hero search, component search, .searchbox, .control,
    the table filter select) sit at 16px because iOS Safari zooms the page when a focused field is
    smaller, and the finding-band figure is a display number, not a step on a text scale.
    """
    exempt = re.compile(
        r"hero-search input|tw-search__input|tw-field__input\[type=\"search\"\]"
        r"|^\.searchbox input$|^\.control$|^\.tw-filters__select$"
        r"|finding-stat b|^\.brand$"
    )
    for path in [
        PIPELINE / "build_college_pages.py",
        ROOT / "components" / "components.css",
        SITE / "styles.css",
    ]:
        text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.S)
        # head() lives inside an f-string, where a CSS brace is doubled.
        text = text.replace("{{", "{").replace("}}", "}")
        for sel, body in re.findall(r"([^{}]*)\{([^{}]*)\}", text):
            sel = " ".join(sel.split())
            if exempt.search(sel):
                continue
            for size in (s.strip() for s in re.findall(r"font-size:\s*([^;}]+)", body)):
                assert "var(--t-" in size or size == "inherit", (
                    f"{path.name}: ad-hoc type size {size!r} on {sel!r}; use a --t-* token"
                )


def test_the_profile_argument_is_set_in_the_editorial_serif():
    """The role split says body is UI sans and editorial prose is the serif, but on a profile page
    the verdict sentence and the payback explanation ARE the argument, and both inherited body
    sans. They also inherited the 860px width the program table needs, which put prose at roughly
    115 characters a line. Serif plus a measure, on the two elements that carry the reasoning."""
    src = (PIPELINE / "build_college_pages.py").read_text()
    for cls in (".verdict", ".calc-big"):
        rule = re.search(rf"\n\s*{re.escape(cls)} \{{\{{(.+?)\}}\}}", src)
        assert rule, f"{cls} rule not found in head()"
        body = rule.group(1)
        assert "var(--display)" in body, f"{cls} should carry the editorial serif"
        assert "var(--measure)" in body, f"{cls} should be capped at a reading measure, not 860px"


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
    # The wrapper carries tabindex, role and aria-label now, so match the class rather than a
    # fixed opening string: the point is that a table is wrapped, not how the tag is spelled.
    wrapped = re.compile(r'<div class="tscroll"[^>]*><table class="t')
    for gen in GENERATORS:
        src = (PIPELINE / gen).read_text()
        opens = len(wrapped.findall(src))
        closes = src.count("</tbody></table></div>")
        assert opens > 0, f"{gen} should wrap its tables in .tscroll"
        assert opens == closes, (
            f"{gen} has unbalanced tscroll wrappers ({opens} open, {closes} close)"
        )
    # No table may be emitted outside a wrapper.
    for gen in GENERATORS:
        src = (PIPELINE / gen).read_text()
        assert src.count('<table class="t') == len(wrapped.findall(src))


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


def test_a_match_count_is_never_stated_against_rows_that_were_not_searched():
    """245 profiles keep most of their programs behind a fetch, and the count line said "3 of 489
    programs match" while 339 of those 489 had never been read.

    That is the ZZ defect in a different surface. The hub gave 461 unassessable schools a clean bill
    of health; here a search reported a result over a set it had examined part of. Both state a
    conclusion about rows the code has not seen.

    The repair has two halves, and this holds both. Interaction loads the whole set, so the normal
    path searches everything. And when that fetch fails the denominator must shrink to what is
    loaded, with the gap named, rather than quietly keeping the larger number.
    """
    js = (ROOT / "components" / "table.js").read_text()

    # Every interaction that reads across rows must ask for the whole set first.
    for interaction in (
        'filters.addEventListener("focusin"',  # the Degree menu is built from loaded rows
        "_ensureWholeSet();",
    ):
        assert interaction in js, f"missing the whole-set guard: {interaction}"
    assert js.count("_ensureWholeSet()") >= 5, (
        "search, both filters, both sort controls and the filter block should each ensure the whole "
        "set; one of them searching a partial list is enough to reproduce the defect"
    )

    # The disclosure branch: a failed tail must describe the set it searched.
    assert "programs loaded match" in js, (
        "a failed tail must count against the loaded rows, not the full total"
    )
    assert "not been searched" in js, "a failed tail must say the unfetched rows were not searched"
    # And it must not be retried silently in a way that leaves the claim stale.
    assert "this.tailFailed = true" in js, "a failed tail must be recorded, not forgotten"


def test_revealing_more_rows_never_drops_focus_to_the_document():
    """ "Show more" focused the button it had just clicked. Two problems.

    The button sits below the rows it reveals, so a keyboard or screen-reader user was put past the
    content they asked for. And on the final click the button is removed, because nothing is left to
    reveal, so there was nothing to focus: focus fell to <body> and the reader was returned to the
    top of the document at the moment they finished opening the list.

    Both surfaces with a reveal are checked, because the Careers page carries its own copy of this
    logic rather than using the component.
    """
    js = (ROOT / "components" / "table.js").read_text()
    assert "const firstNew = this.shown" in js, (
        "the component must remember where the new rows start"
    )
    assert "landing.focus()" in js, "focus must move to a row, which always exists"
    assert 'landing.setAttribute("tabindex", "-1")' in js, (
        "the landing row must be focusable without becoming a tab stop"
    )

    careers = (SITE / "careers" / "index.html").read_text()
    assert 'document.getElementById("cr-more")?.focus()' not in careers, (
        "Careers still focuses the button, which is absent on the last reveal"
    )
    assert "const firstNew = shown" in careers, "Careers must remember where the new rows start"
    assert "landing.focus()" in careers, "Careers must move focus to a row"
    assert 'id="cr-live"' in careers and 'role="status"' in careers, (
        "moving focus into a table announces a row, not a count; Careers needs a live region to say "
        "how many arrived"
    )


def test_a_profile_description_states_the_size_that_separates_two_same_named_campuses():
    """After the place went into titles, 13 title values were still shared by 26 pages and 10
    description values by 20. Every one is two real institutions reporting under the same name.

    Seven are separate campuses in the SAME city, so the place cannot tell them apart. The other six
    are in the 461 that file program data but have no institution record at all, so there is no city
    and no state to use. Those 461 are exactly the ZZ population: the same root cause, surfacing a
    second time.

    Checked against the source before writing the fix: all 13 pairs differ in programs reported,
    distinct CIP codes, or recent completers. None is one record twice. So a real fact separates them,
    and it is the one a reader comparing two same-named campuses wants. Saying it resolves all ten
    description collisions without inventing a suffix, a letter or a UNITID, none of which tell a
    reader anything.
    """
    src = (PIPELINE / "build_canonical_profiles.py").read_text()
    assert 'size = f"Reports {total} program' in src, (
        "the description must carry the program count that separates same-named campuses"
    )
    assert "recent graduate" in src, "and the graduate count, which differs where programs tie"
    # All three description branches must carry it, or the branch that omits it reintroduces the
    # collision. The no-verdict branch matters most: six of the ten collisions were in it.
    assert src.count("{size}") == 3, (
        f"all three description branches need the size clause, found {src.count('{size}')}"
    )
    # Not a fabricated distinguisher. A UNITID in a description identifies a row, not an institution.
    desc_block = src.split("# Honest headline", 1)[1].split("# Title carries", 1)[0]
    assert "unitid" not in desc_block.lower(), (
        "a UNITID in the description distinguishes strings rather than institutions"
    )


# The 13 title collisions that remain after the place went into every title, approved as
# irreducible on 2026-09-11. Each is two real institutions reporting to the Department of Education
# under one name: seven are separate campuses in the SAME city, so the place cannot separate them,
# and six are among the 461 that file programme data with no institution record at all, so there is
# no city and no state to use.
#
# The decision was to keep them rather than invent a discriminator. A UNITID, a letter or a numeric
# suffix in a title separates strings, not institutions, and tells a reader nothing. What does
# separate them is carried where it belongs: the URLs are unique, and the descriptions now state
# programmes and recent graduates, which differs for all 13 pairs.
#
# This list is an allowlist, not a tolerance. A collision that is not in it is a new defect, most
# likely a template regression that would hit far more than two pages, and it must fail.
KNOWN_TITLE_COLLISIONS = frozenset(
    {
        frozenset({"larry-s-barber-college-il", "larry-s-barber-college"}),
        frozenset({"city-college-hollywood-zz", "city-college-hollywood"}),
        frozenset({"western-technical-college-tx", "western-technical-college-224660"}),
        frozenset({"cortiva-institute-438285", "cortiva-institute-387925"}),
        frozenset(
            {"international-school-of-cosmetology", "international-school-of-cosmetology-zz"}
        ),
        frozenset({"trend-barber-college-tx", "trend-barber-college"}),
        frozenset({"tulsa-welding-school-jacksonville-fl", "tulsa-welding-school-jacksonville"}),
        frozenset({"royal-learning-institute", "royal-learning-institute-zz"}),
        frozenset({"mitchells-academy", "mitchells-academy-zz"}),
        frozenset({"ideal-beauty-academy", "ideal-beauty-academy-zz"}),
        frozenset({"american-university-of-puerto-rico-zz", "american-university-of-puerto-rico"}),
        frozenset({"interactive-college-of-technology-tx", "interactive-college-of-technology"}),
        frozenset(
            {"southern-careers-institute-san-antonio", "southern-careers-institute-san-antonio-tx"}
        ),
    }
)


def test_no_college_title_collides_outside_the_approved_thirteen():
    """An allowlist, so an accidental collision still fails.

    The template fix took duplicate titles from 86 values over 202 pages down to 13 over 26. Marking
    the remainder "known" without pinning them would mean the next template change could reintroduce
    mass duplication and this suite would call it expected. Each approved pair is named, so a new
    one, or a pair that stops colliding and should be removed from the list, both show up.
    """
    col = SITE / "college"
    pages = sorted(col.glob("*/index.html")) if col.exists() else []
    if len(pages) < 1000:
        pytest.skip("no built college tree in this working copy")

    by_title: dict[str, set[str]] = {}
    for p in pages:
        m = re.search(r"<title>(.*?)</title>", p.read_text(), re.S)
        if m:
            by_title.setdefault(m.group(1), set()).add(p.parent.name)

    groups = {frozenset(s) for s in by_title.values() if len(s) > 1}
    unexpected = groups - KNOWN_TITLE_COLLISIONS
    assert not unexpected, (
        "new duplicate title groups, which usually means a template regression rather than two "
        f"same-named schools: {[sorted(g) for g in unexpected]}"
    )
    stale = KNOWN_TITLE_COLLISIONS - groups
    assert not stale, (
        "these pairs no longer collide, so remove them from KNOWN_TITLE_COLLISIONS rather than "
        f"leaving an allowlist that grants more than it needs to: {[sorted(g) for g in stale]}"
    )


def test_no_two_college_pages_share_a_description():
    """Zero tolerance here, unlike titles, because the description has room for the fact that
    separates them. All 13 colliding pairs differ in programmes reported, distinct CIP codes or
    recent completers, so every one can be told apart in a sentence."""
    col = SITE / "college"
    pages = sorted(col.glob("*/index.html")) if col.exists() else []
    if len(pages) < 1000:
        pytest.skip("no built college tree in this working copy")

    by_desc: dict[str, list[str]] = {}
    for p in pages:
        m = re.search(r'<meta name="description" content="(.*?)"', p.read_text(), re.S)
        if m:
            by_desc.setdefault(m.group(1), []).append(p.parent.name)
    dupes = {k: v for k, v in by_desc.items() if len(v) > 1}
    assert not dupes, f"{len(dupes)} duplicate description groups: {list(dupes.values())[:5]}"


def test_careers_carries_its_data_without_javascript():
    """Careers was the one data page that degraded to nothing.

    The table was built entirely in the browser from a 785 KB JSON, so with scripting off a reader
    got a paragraph pointing at the methodology page. Approved on 2026-09-11 as a defect rather than
    a contract exception: the profile pages have shipped a static core since Stage 4.1 and this is
    the same contract at the same page size.
    """
    html = (SITE / "careers" / "index.html").read_text()
    core = html.split("<!-- CAREERS_CORE_START -->", 1)
    assert len(core) == 2, "the careers core markers are missing, so build_careers cannot write it"
    core = core[1].split("<!-- CAREERS_CORE_END -->", 1)[0]

    rows = core.count("<tr data-cip")
    assert rows == 25, f"the static core should carry one page of 25 rows, found {rows}"
    # The full total must be stated, or 25 rows imply the dataset is 25 rows long.
    assert re.search(r"Showing 25 of [\d,]+", core), (
        "the core must state the whole set, not only what it shows"
    )
    # Links go to permanent major pages, NOT to the page's own ?field= route, which is itself
    # rendered in the browser and would hand a no-JavaScript reader a second empty page.
    assert core.count('href="/majors/') == rows, "every static row must link to its major page"
    assert "?field=" not in core, (
        "a static row must not link into the client-rendered detail view, which needs the script it "
        "is standing in for"
    )
    # And the noscript text must no longer claim there is nothing to read here.
    assert "This interactive view needs JavaScript to run" not in html, (
        "the noscript message still says the view needs JavaScript, which is now false: the table is"
        " in the HTML"
    )


def test_careers_announces_a_changed_count_and_not_only_a_reveal():
    """Narrowing the Careers list must be announced, not only revealing more of it.

    Found by the layout check on its first real run. `cr-live` was written in exactly ONE place, the
    Show more handler. Search, the family filter and sort all went through redraw() and never
    touched it, so going from 738 combinations to 13 was silent. And because the region kept its
    previous contents, a reader who revealed 50 rows and then searched was left with the region
    reading "25 more shown. Showing 50 of 738" over a list of 13. Stale is worse than silent,
    because it is false.

    components/table.js has carried this fix since the browser rounds; Careers is a separate code
    path and never got it.
    """
    src = (SITE / "careers" / "index.html").read_text()

    # Strip comments ONCE, at the top, before any assertion reads the source.
    #
    # This is the sixth-plus occurrence of a check on this project matching the prose that describes
    # a fix rather than the code performing it, and the comment added beside THIS fix names
    # "live.textContent", "redraw" and "Show more" precisely because it is explaining what was
    # missing. Asserting against the raw file would pass on the explanation alone.
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    code = re.sub(r"<!--.*?-->", "", code, flags=re.S)
    code = "\n".join(re.sub(r"(?<!:)//.*$", "", ln) for ln in code.splitlines())

    assert "const announce" in code, "the announcement helper is gone"
    # redraw() is what search, the family filter and sort all call. If it does not announce, none of
    # the three does.
    m = re.search(r"const redraw = \(\) => \{([^}]*)\}", code)
    assert m, "redraw() is no longer recognisable, so this guard cannot check it"
    assert "announce()" in m.group(1), (
        "redraw() must announce the new count; without it search, the family filter and sort are "
        "all silent, which is the defect this test exists for"
    )
    # The initial render must NOT announce: a live region that speaks on page load is noise.
    tail = code.split("const redraw", 1)[1]
    assert re.search(r"\n\s*draw\(\);\s*\n\s*q\.focus\(\);", tail), (
        "the initial draw() should stay a plain draw, with no announcement on first paint"
    )


def test_every_k12_ranking_metric_gets_a_sentence_that_parses():
    """One sentence template did not fit all nine metrics, and the ternary meant to fix it had two
    identical branches.

    Eight metrics are a share of high schools and read correctly. The ninth is a state median ratio,
    and it shipped as "States where the most high schools students per counselor (state median) are
    at the top." That is not a sentence, and it was live.

    Duplicated ternary branches are the tell: something was meant to differ and never did. This
    guard asserts on the METRICS table itself rather than on one known-bad string, so adding a
    tenth metric with a new unit fails here rather than on the page.
    """
    src = (SITE / "k12" / "rankings" / "index.html").read_text()
    # Comments stripped once, at the top. The comment beside this fix quotes the broken sentence
    # verbatim to explain it, so asserting on the raw file would pass on the explanation.
    code = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)

    block = code.split("const METRICS = [", 1)[1].split("];", 1)[0]
    units = set(re.findall(r'unit:"([^"]+)"', block))
    assert units == {"%", ":1"}, f"a new metric unit appeared: {units}; the sentence must handle it"

    # The share template must appear exactly once. Twice means the duplicated-branch bug is back.
    assert code.count("are at the top.") == 1, (
        "the 'are at the top' template appears more than once, which is how the identical-branch "
        "ternary looked before it was fixed"
    )
    assert 'm.unit === ":1"' in code, "the ratio metric has no sentence of its own"
    # Direction must be stated: six metrics are good at the top and three are bad, and the list
    # looks the same either way.
    assert "the worse end" in code, "a hiWorst ranking must say the top is the bad end"


def test_the_k12_pages_announce_when_their_results_change():
    """Careers was silent on search because it was a separate code path from components/table.js.
    So are the K-12 pages, and two of them had no live region at all: compare returned search hits
    silently, and rankings replaced the entire ranked list on a select change without a word.
    """
    comp = (SITE / "k12" / "compare" / "index.html").read_text()
    comp_code = re.sub(r"/\*.*?\*/", "", re.sub(r"<!--.*?-->", "", comp, flags=re.S), flags=re.S)
    assert 'id="k12-live"' in comp_code and 'aria-live="polite"' in comp_code
    assert comp_code.index('id="k12-live"') < comp_code.index('id="results"'), (
        "the live region must come before the list it describes"
    )
    # Search, add and remove all change what is on screen, so all three must speak.
    assert comp_code.count("announce(") >= 3, "search, add and remove must each announce"

    rank = (SITE / "k12" / "rankings" / "index.html").read_text()
    rank_code = re.sub(r"<!--.*?-->", "", rank, flags=re.S)
    assert re.search(r'id="sub"[^>]*role="status"', rank_code), (
        "the ranking subtitle is the live region; changing the metric must be announced"
    )


def test_a_bar_whose_width_is_set_in_js_is_not_an_inline_element():
    """The K-12 ranking drew 52 bars and every one measured 0px wide.

    `.fill` is a <span>, so it is display:inline, and width does not apply to an inline
    non-replaced element. Massachusetts at width:100% and Puerto Rico at width:5% rendered
    identically: nothing. The percentages printed beside them were correct, so the page looked
    populated rather than broken, and it survived a full redesign and three rounds of review.

    Any element whose width is set from JavaScript has to be block, inline-block, flex, grid, or
    absolutely positioned. The Careers range bar gets away with a <i> only because it is
    position:absolute, which makes the box block-level.
    """
    for page, fill_sel in ((SITE / "k12" / "rankings" / "index.html", ".bars .fill"),):
        css = page.read_text()
        rule = re.search(re.escape(fill_sel) + r"\s*\{([^}]*)\}", css)
        assert rule, f"{fill_sel} has no rule in {page.name}"
        body = rule.group(1)
        assert re.search(r"display:\s*(block|inline-block|flex|grid)", body) or re.search(
            r"position:\s*absolute", body
        ), f"{fill_sel} sets a width from JS but is not block-level, so the bar renders at 0px"


def test_the_k12_not_offered_and_not_reported_labels_are_legible():
    """`.no` (not offered) and `.na` (not reported) are the two labels the missingness work exists
    to keep apart, and they shipped in #98a1b0: 2.50:1 on paper, against a 4.5:1 AA minimum. The
    distinction the data careful about was the hardest text on the page to read.

    Asserting on the hex rather than recomputing the ratio here, because tests/test_contrast.py
    already does real WCAG math over the palette; this only has to stop the raw value coming back.

    Comments stripped first. The comment added beside the fix names the hex it removed in order to
    explain it, so the first version of this guard found the value in its own explanation and failed
    on a page that had been fixed. That is the third time in one session that a check has matched the
    prose describing a fix rather than the code performing it, which is now less a mistake than a
    property of writing checks against files that document themselves.
    """
    for name in (
        "index.html",
        "rankings/index.html",
        "compare/index.html",
        "advanced-courses/index.html",
    ):
        raw = (SITE / "k12" / name).read_text()
        css = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        assert "#98a1b0" not in css, (
            f"k12/{name} still uses #98a1b0, which fails AA at 2.50:1; use var(--none) at 5.78:1"
        )


def test_every_inline_script_on_a_hand_written_page_parses(tmp_path):
    """Value Check shipped with a script that could not parse, and every test passed.

    A comment added to explain a fix sat inside a JavaScript template literal and wrote a word in
    backticks. A backtick ends a template literal, so the whole 40 KB application became a syntax
    error: "Unexpected identifier 'live'". The page the main "Find a college" button leads to
    showed its loading paragraph and never drew a search box. Nothing in the suite noticed,
    because the smoke tests load helper modules and fragments, not the page's own script as the
    browser does.

    So: every inline script on every hand-written page is handed to `node --check`, which parses
    without running. It is the cheapest possible test and it covers the failure that matters
    most, a page that does not start at all.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed, so inline scripts cannot be parsed here")

    generated = re.compile(r"^(college|colleges|majors|lists|og)/")
    block = re.compile(
        r"<script(?![^>]*\ssrc=)(?![^>]*application/(?:ld\+)?json)[^>]*>([\s\S]*?)</script>"
    )
    checked, failures = 0, []
    for page in sorted(SITE.rglob("*.html")):
        rel = page.relative_to(SITE).as_posix()
        if generated.match(rel):
            continue
        for i, code in enumerate(block.findall(page.read_text(errors="ignore"))):
            if not code.strip():
                continue
            f = tmp_path / f"{rel.replace('/', '_')}_{i}.js"
            f.write_text(code)
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            checked += 1
            if r.returncode:
                failures.append(f"{rel} script {i}: {r.stderr.strip().splitlines()[-1]}")
    assert checked >= 5, f"only {checked} inline scripts found; the page scan itself is broken"
    assert not failures, "inline scripts that do not parse:\n" + "\n".join(failures)


def test_the_profile_program_table_fits_a_laptop_and_keeps_program_names_whole():
    """The program table needed 1,058px in an 858px column at 1280px, and the Program column came out
    narrowest of eight at 87px, so names split inside words ("Financ / e", "Informat / ion").

    Measured fix, all eight sampled profiles fitting with no horizontal scroll: headers may wrap,
    Program has a 10em floor, the 1-year marker may wrap, "insufficient data" runs at fine size, the
    premium bar is 32px and side padding is one spacing step. Each rule below is one of those, so
    removing any of them brings a column's width back above what the page can hold.
    """
    raw = (ROOT / "components" / "components.css").read_text()
    css = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)

    def rule(selector):
        m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
        assert m, f"{selector} rule is missing from components.css"
        return m.group(1)

    assert "nowrap" not in rule(".tw-th"), (
        "table headers held on one line set the column widths again"
    )
    assert re.search(r"min-width:\s*10em", rule(".tw-td--program")), (
        "Program lost its width floor; below it, overflow-wrap:anywhere splits ordinary words"
    )
    assert "nowrap" not in rule(".tw-oneyr"), (
        "the 1-year marker on one line widens the earnings column"
    )
    assert "var(--t-fine)" in rule(".tw-td__insuf"), (
        "'insufficient' at body size widens every numeric column"
    )
    assert re.search(r"width:\s*32px", rule(".tw-prem__bar")), "the premium bar grew back"


def test_careers_stacks_on_phones_and_never_shows_unknown_as_a_value():
    """At 390px the Careers table was 801px wide in a 348px window, so the earnings column, the one
    number the page exists to show, began at the right edge of the screen. "Show 25 more" was an
    unstyled browser button 22px tall. And an unknown pass rate printed "n/a" and took the red "lo"
    class, drawn like a failing major, while a row with no earnings range still drew a stub bar.
    """
    src = (SITE / "careers" / "index.html").read_text()
    code = re.sub(r"/\*.*?\*/", "", re.sub(r"<!--.*?-->", "", src, flags=re.S), flags=re.S)

    core = src.split("<!-- CAREERS_CORE_START -->", 1)[1].split("<!-- CAREERS_CORE_END -->", 1)[0]
    rows = core.count("<tr data-cip")
    assert core.count('data-label="') == rows * 5, (
        "every non-name static cell needs its column label"
    )

    assert re.search(r"@media \(max-width: 768px\)[^@]*\.cr-table thead \{ display: none", code), (
        "the phone layout that stacks rows into cards is gone"
    )
    assert 'class="btn btn--secondary" id="cr-more"' in code, (
        "the Show more button lost its style; it should be the shared secondary button"
    )
    assert '"n/a"' not in code and ">n/a<" not in src, "unknown must read 'insufficient data'"
    assert 'f.pass_pct == null ? "unk"' in code, (
        "an unknown pass rate must not borrow the failing colour"
    )


def test_every_hand_written_page_uses_the_one_shared_header():
    """Three K-12 pages kept an old header after the others were unified: "Find a college" first
    rather than last, no About link, no brand tagline, and no mobile menu at all, so on a phone
    those pages had no way to reach the rest of the site except the logo.

    Compared against the header on a generated college profile, which is what 6,500+ pages carry.
    Whitespace is normalised, and so is aria-current, the one attribute a page is meant to set for
    itself (it marks that page's own nav link). Anything else that differs is a second header.
    """

    def header(text):
        m = re.search(r'<header class="site-header">.*?</header>', text, re.S)
        if not m:
            return None
        return re.sub(r"\s+", " ", re.sub(r' aria-current="[^"]*"', "", m.group(0)))

    reference = header(next((SITE / "college").glob("*/index.html")).read_text())
    assert reference and "nav-toggle" in reference, "the reference header lost its mobile menu"
    generated = re.compile(r"^(college|colleges|majors|lists|og|embed)/")
    odd = []
    for page in sorted(SITE.rglob("index.html")):
        rel = page.relative_to(SITE).as_posix()
        if generated.match(rel):
            continue
        h = header(page.read_text(errors="ignore"))
        if h is not None and h != reference:
            odd.append(rel)
    assert not odd, "pages with a header that differs from the shared one: " + ", ".join(odd)


def test_hand_written_pages_carry_no_old_blue():
    """The site moved to the forest palette, but five hand-written pages kept the old blue.

    Careers drew its earnings range in #bcd3f5 on #eef1f6 tracks, and seven hover and focus shadows
    across Value Check, Careers and the K-12 cards were tinted rgba(31,111,235). On a green site the
    blue read as a leftover, and the range band at 1.35:1 against its track was barely visible. The
    replacements are tokens (series-3, line-soft, brand-50) or an ink tint for shadows.

    Comments stripped, since a comment explaining a fix may name the value it removed.
    """
    old = ("31,111,235", "#bcd3f5", "#eef1f6", "#1f6feb")
    for page in sorted(SITE.glob("**/index.html")):
        rel = page.relative_to(SITE).as_posix()
        if rel.split("/")[0] in {"school", "state", "majors", "lists", "findings"}:
            continue
        text = re.sub(r"<!--.*?-->", "", page.read_text(), flags=re.S)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"\s+", "", text).lower()
        for value in old:
            assert value.replace(" ", "") not in text, f"{rel} still uses the old blue {value}"


def test_page_titles_and_ledes_use_the_type_tokens():
    """Page titles came in five sizes (41.6 to 48px) and ledes in three, one per hand-written page.

    Every page title, section heading and lede on a hand-written page now takes its size from the
    type tokens, the same ones the generated pages use, so moving between Careers, a profile and
    Methodology no longer changes the size of the thing that says where you are. The homepage hero
    keeps --t-display as the single exception, and it lives in styles.css, not here.
    """
    pages = [
        "value-check/index.html",
        "compare/index.html",
        "careers/index.html",
        "k12/index.html",
        "k12/rankings/index.html",
        "k12/compare/index.html",
        "k12/advanced-courses/index.html",
        "methodology/index.html",
        "about/index.html",
    ]
    for page in pages:
        css = re.sub(r"/\*.*?\*/", "", (SITE / page).read_text(), flags=re.S)
        for sel, body in re.findall(r"([^{}\n]*\b(?:h1|h2|\.lede)\b[^{}\n]*)\{([^}]*)\}", css):
            size = re.search(r"font-size:\s*([^;]+)", body)
            if not size or "<" in sel or "`" in sel:
                continue
            assert size.group(1).strip().startswith("var(--t-"), (
                f"{page}: {sel.strip()} sets font-size {size.group(1).strip()}, use a type token"
            )


HAND_WRITTEN_APP_PAGES = [
    "value-check/index.html",
    "compare/index.html",
    "careers/index.html",
    "k12/index.html",
    "k12/rankings/index.html",
    "k12/compare/index.html",
    "k12/advanced-courses/index.html",
    "404.html",
]


def test_every_form_control_uses_the_one_control_spec():
    """Search boxes and selects came in four heights (35 to 48px) and four radii (0 to 12px).

    Most drew their edge in --line, which is too faint to meet the 3:1 non-text contrast a control
    boundary needs, and Careers set 15px text, which makes iOS Safari zoom the page on focus. Every
    select and text field on a hand-written page now takes .control, or sits in a .searchbox, both
    defined once in styles.css. A page may set a search box's margin and nothing else.
    """
    for page in HAND_WRITTEN_APP_PAGES:
        src = (SITE / page).read_text()
        code = re.sub(r"/\*.*?\*/", "", re.sub(r"<!--.*?-->", "", src, flags=re.S), flags=re.S)
        for tag in re.findall(r"<select\b[^>]*>", code):
            assert 'class="control"' in tag, f"{page}: {tag} should use the shared .control"
        # An input inside the shared .searchbox is styled by it, so it takes no class of its own.
        outside = re.sub(r'<div class="searchbox">.*?</div>', "", code, flags=re.S)
        for tag in re.findall(r"<input\b[^>]*>", outside):
            if re.search(r'type="(hidden|checkbox|radio)"', tag):
                continue
            assert 'class="control"' in tag, f"{page}: {tag} should use the shared .control"
        for body in re.findall(r"\n\s*\.searchbox \{([^}]*)\}", code):
            props = {p.split(":")[0].strip() for p in body.split(";") if ":" in p}
            assert props <= {"margin"}, f"{page}: .searchbox restyles {props - {'margin'}}"


def test_buttons_come_in_three_styles():
    """Primary buttons used 3px corners on the homepage and 10px elsewhere, at heights from 22 to
    47px. Generated primary links and download buttons now use .btn and .btn--secondary from
    styles.css, which is where all three styles are defined."""
    css = (SITE / "styles.css").read_text()
    for sel in (".btn {", ".btn--secondary {", ".btn--text {"):
        assert sel in css, f"styles.css lost {sel}"
    for gen in (
        "build_college_pages.py",
        "build_majors_pages.py",
        "build_stats_exposure.py",
        "build_lists.py",
    ):
        text = (PIPELINE / gen).read_text()
        assert 'class="primary"' not in text and 'class="dl-btn"' not in text, (
            f"{gen} still emits a one-off button class"
        )


def test_hand_written_pages_use_colour_and_radius_tokens():
    """23 raw colours and 9 off-scale radii lived in the hand-written pages' CSS.

    They were the old slate and the old red and green (#6b7688, #b42318, #067647), a gold from a
    retired palette, white, and corners of 9, 12 and 14px on a 3 / 6 / 10px scale. None failed
    contrast; together they are why the app pages looked slightly off-brand next to the profiles.
    Every colour and radius in a hand-written page's CSS is now a token. Shadows may use the ink
    tint rgba(12,21,18,...), since the palette defines no shadow token, and a circle may use 50%.
    """
    for page in [*HAND_WRITTEN_APP_PAGES, "methodology/index.html", "about/index.html"]:
        src = (SITE / page).read_text()
        css = "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", src, flags=re.S))
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
        assert not hexes, f"{page}: raw colours {sorted(set(hexes))}; use palette tokens"
        rgbas = [c for c in re.findall(r"rgba?\([^)]*\)", css) if not c.startswith("rgba(12,21,18")]
        assert not rgbas, f"{page}: raw colours {sorted(set(rgbas))}; use tokens or the ink tint"
        for value in re.findall(r"border-radius:\s*([^;}]+)", css):
            for part in value.split():
                assert part in {"0", "50%"} or part.startswith("var(--r"), (
                    f"{page}: border-radius {value.strip()!r} is off the 3/6/10px scale"
                )


def test_the_primary_nav_says_where_you_are():
    """On /careers/ the Careers link looked identical to the other four, while the K-12 subnav did
    show its active tab. Each section page now marks its own nav link aria-current, in the static
    markup so it holds without JavaScript, and styles.css underlines it."""
    expected = {
        "careers/index.html": ("/careers/", "page"),
        "methodology/index.html": ("/methodology/", "page"),
        "about/index.html": ("/about/", "page"),
        "value-check/index.html": ("/value-check/", "page"),
        "k12/index.html": ("/k12/", "page"),
        "k12/rankings/index.html": ("/k12/", "true"),
        "k12/compare/index.html": ("/k12/", "true"),
        "k12/advanced-courses/index.html": ("/k12/", "true"),
    }
    for page, (href, value) in expected.items():
        html = (SITE / page).read_text()
        nav = re.search(r'<nav aria-label="Primary">(.*?)(?:<details|</nav>)', html, re.S).group(1)
        current = re.findall(r'<a[^>]*href="([^"]+)"[^>]*aria-current="([^"]+)"', nav)
        assert current == [(href, value)], f"{page}: primary nav marks {current}, want {href}"
    css = (SITE / "styles.css").read_text()
    assert "nav a[aria-current]" in css, "the current nav link has no visible style"


def test_phase_three_polish_holds():
    """Four small fixes from the design pass, each of which had a reader-facing cost.

    Value Check opened as a paragraph ending "Loading the data now", with no search box until the
    script ran; during the template-literal outage that paragraph was the whole page. The static
    first view is now the search view with the box disabled and a browse link that needs no script.
    Compare drew coverage below 50% in the failing red, which is nearly every school. K-12 Compare
    printed "n/a" for a missing count. Methodology ran about 95 characters a line.
    """
    vc = (SITE / "value-check" / "index.html").read_text()
    boot = vc.split('<div id="boot-fallback">', 1)[1].split("</main>", 1)[0]
    assert 'class="searchbox"' in boot and " disabled" in boot, "no static, disabled search box"
    assert 'href="/colleges/"' in boot, "the static view needs a route that works without script"

    cmp_src = (SITE / "compare" / "index.html").read_text()
    measured = cmp_src.split('row("Programs measured"', 1)[1].split("}));", 1)[0]
    assert '"bad"' not in measured, "coverage must not take the colour of a failing result"

    k12 = re.sub(
        r"/\*.*?\*/", "", (SITE / "k12" / "compare" / "index.html").read_text(), flags=re.S
    )
    assert '"n/a"' not in k12, "K-12 unknowns read 'Not reported', never 'n/a'"

    meth = (SITE / "methodology" / "index.html").read_text()
    assert ".doc p, .doc li { max-width: var(--measure); }" in meth, (
        "Methodology prose lost its measure"
    )
