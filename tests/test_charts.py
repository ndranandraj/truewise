"""Release 3 B4: the chart usage matrix, enforced rather than trusted.

Section 8 of the forest decision record says the colour ramp can never carry meaning alone: clay is
the only negative, light fills need an outline, and every mark must clear 3.0 against the surface it
sits on while text clears 4.5. These recompute the ratios from the palette instead of asserting
remembered numbers, so a future palette edit fails here rather than shipping a chart nobody can read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline import tokens_gen as tk

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
SITE = ROOT / "site"
PALETTE = json.loads((ROOT / "design" / "palette-final.json").read_text())
BRAND_DEEP = PALETTE["surfaces"]["brand-strong"]
PAPER = PALETTE["surfaces"]["paper"]

# Pre-forest colours that predate the token pipeline: two gradient stops from the premium bars and
# the three golds from the "hidden gem" pill. None can follow the palette, so none may come back.
STALE = ("#17936a", "#c23522", "#fff7e6", "#8a6d1a", "#f0d999")


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    ch = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    return round((max(la, lb) + 0.05) / (min(la, lb) + 0.05), 2)


def _home_chart_block() -> str:
    """The chart block as actually published, not as the generator would render it."""
    html = (SITE / "index.html").read_text()
    m = re.search(r"<!-- HOME_CHART_START -->(.*?)<!-- HOME_CHART_END -->", html, re.S)
    assert m, "the homepage lost its HOME_CHART markers"
    return m.group(1)


def _variant(cls: str) -> str:
    block = _home_chart_block()
    m = re.search(rf'<figure class="home-dist {cls}"[^>]*>(.*?)</figure>', block, re.S)
    assert m, f"the {cls} chart variant is missing"
    return m.group(1)


def _home_chart_svg() -> str:
    """The wide variant, which carries the approved desktop geometry."""
    return _variant("home-dist--wide")


def test_the_negative_bar_uses_the_dark_band_clay_not_sand():
    """The 'earn less' bar rendered in --band-accent (sand), so the one negative in the whole
    system was carrying no negative colour at all. True clay is 1.89 on the band, so B4 approved
    the dark-band clay tint instead."""
    svg = _home_chart_svg()
    assert tk.SERIES_NEG_ON_DARK in svg, "the negative bar is not using the dark-band clay tint"
    assert tk.BAND_ACCENT not in re.findall(r'<rect[^>]*fill="([^"]+)"', svg), (
        "a bar is still filled with the sand band accent"
    )


def test_every_home_chart_mark_and_label_clears_its_threshold():
    """Marks need 3.0 on the band, text needs 4.5. The clay tint satisfies the first and not the
    second, which is exactly why the labels must not be tinted to match the bar."""
    svg = _home_chart_svg()
    for colour in re.findall(r'<(?:rect|line)[^>]*(?:fill|stroke)="(#[0-9a-fA-F]{6})"', svg):
        ratio = contrast(colour, BRAND_DEEP)
        assert ratio >= 3.0, f"chart mark {colour} is {ratio} on the band, under 3.0"
    for colour, label in re.findall(r'<text[^>]*fill="(#[0-9a-fA-F]{6})"[^>]*>([^<]*)</text>', svg):
        ratio = contrast(colour, BRAND_DEEP)
        assert ratio >= 4.5, f"chart label {label!r} is {colour} at {ratio} on the band, under 4.5"


def test_home_chart_matches_the_approved_geometry():
    """The rebrand plan specifies viewBox 480x260, 42px bars, a 14px gap and 13px labels. The
    chart shipped at 360x230 with 9.5px labels on 32px bars, which is under the 12px floor the
    record sets for mono metadata and too small to read on a phone."""
    svg = _home_chart_svg()
    assert 'viewBox="0 0 480 260"' in svg, "chart is not on the approved 480x260 canvas"
    widths = {int(w) for w in re.findall(r"<rect[^>]*width=\"(\d+)\"", svg)}
    assert widths == {42}, f"bars must be 42 wide, found {sorted(widths)}"
    xs = [int(x) for x in re.findall(r'<rect x="(\d+)"', svg)]
    gaps = {xs[i + 1] - xs[i] - 42 for i in range(len(xs) - 1)}
    assert gaps == {14}, f"bar gaps must be 14, found {sorted(gaps)}"
    sizes = {float(s) for s in re.findall(r'font-size="([\d.]+)"', svg)}
    assert sizes == {13.0}, f"in-chart labels must be 13px, found {sorted(sizes)}"
    assert 'style="max-width:480px' in svg, "the wide chart must not stretch past its geometry"
    # Mono comes from the stylesheet rather than an SVG attribute, so it follows the token.
    css = (SITE / "styles.css").read_text()
    assert ".home-dist text" in css and "var(--mono)" in css.split(".home-dist text", 1)[1][:120], (
        "chart labels must be mono, per the type roles"
    )


def _gutter(viewport: int) -> int:
    """The .wrap horizontal padding at a viewport, read from site/styles.css.

    Read rather than hardcoded, so this test cannot quietly disagree with the layout.
    """
    css = (SITE / "styles.css").read_text()
    scale = dict(re.findall(r"--(s\d+):\s*(\d+)px", css))
    wide = scale[re.search(r"\.wrap \{[^}]*padding: 0 var\(--(s\d+)\)", css).group(1)]
    narrow = re.search(
        r"@media \(max-width: (\d+)px\) \{ \.wrap \{ padding: 0 var\(--(s\d+)\)", css
    )
    return int(scale[narrow.group(2)] if viewport <= int(narrow.group(1)) else wide)


def _displayed(viewport: int) -> str:
    """Which variant CSS actually shows at this viewport, read from the media query."""
    css = (SITE / "styles.css").read_text()
    swap = int(re.search(r"@media \(max-width: (\d+)px\) \{\n  \.home-dist--wide", css).group(1))
    return "home-dist--narrow" if viewport <= swap else "home-dist--wide"


def _rendered_label_px(viewport: int) -> tuple[str, float]:
    """On-screen label size of whichever chart is displayed, from its REAL rendered width.

    The width is the column capped by the SVG's own max-width, not an assumption that the column
    is always the viewport minus 40.
    """
    cls = _displayed(viewport)
    svg = _variant(cls)
    vb = int(re.search(r'viewBox="0 0 (\d+)', svg).group(1))
    cap = int(re.search(r"max-width:(\d+)px", svg).group(1))
    width = min(viewport - 2 * _gutter(viewport), cap)
    sizes = {float(s) for s in re.findall(r'font-size="([\d.]+)"', svg)}
    return cls, round(min(sizes) * (width / vb), 2)


def test_chart_labels_stay_legible_at_every_width():
    """font-size inside an SVG is in USER units, so the viewBox transform scales it. An earlier
    test asserted font-size="13" and passed while the 480-wide chart, squeezed into a 335px phone
    column, rendered labels at about 9.1px.

    The breakpoints are the sharp edges. Swapping variants at 520px left a band just above it
    where the wide chart was scaled to 0.92 and rendered 11.9px labels, so the swap is at 560px:
    the narrowest viewport whose column reaches the wide chart's own 480px.
    """
    for viewport in (320, 360, 390, 430, 519, 520, 521, 524, 525, 559, 560, 561, 768, 1440):
        cls, px = _rendered_label_px(viewport)
        assert px >= 12.0, f"at {viewport}px the {cls} chart renders {px}px labels, under 12px"
    for viewport in (390, 559, 560, 1440):
        _cls, px = _rendered_label_px(viewport)
        assert px >= 13.0, f"at {viewport}px labels render at {px}px, expected the full 13px"


def test_exactly_one_chart_is_exposed_to_assistive_tech_at_every_width():
    """Both variants are always in the DOM and CSS shows one. display:none already removes the
    other from the accessibility tree, so neither may ALSO be aria-hidden: when the narrow figure
    carried aria-hidden, a phone had the wide chart display:none and the visible one hidden, so a
    screen reader was offered no chart at all."""
    block = _home_chart_block()
    figures = re.findall(r'<figure class="home-dist ([^"]+)"([^>]*)>', block)
    assert len(figures) == 2, f"expected two chart variants, found {len(figures)}"
    for cls, attrs in figures:
        assert "aria-hidden" not in attrs, (
            f"{cls} is aria-hidden; at the width where it is the DISPLAYED chart that leaves no "
            "chart in the accessibility tree"
        )
    ids = re.findall(r'id="((?:distTitle|distDesc)[^"]*)"', block)
    assert len(set(ids)) == len(ids) == 4, f"chart variants must have distinct ids, got {ids}"
    for viewport in (320, 390, 520, 521, 560, 1440):
        svg = _variant(_displayed(viewport))
        assert "aria-labelledby" in svg and "<title" in svg, (
            f"at {viewport}px the displayed chart is not an accessible named image"
        )


def test_home_chart_shows_its_denominator():
    """The percentages are a share of the judged programs, and a reader should be able to see what
    of without opening the accessibility description. It used to live only in <desc>."""
    svg = _home_chart_svg()
    visible = " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg))
    assert re.search(r"n = [\d,]+ judged programs", visible), (
        "the provenance line is missing from the visible chart"
    )


def test_the_negative_is_labelled_in_words():
    """Colour never carries the meaning on its own."""
    assert "earn less" in _home_chart_svg()


def test_light_chart_fills_carry_an_outline():
    """The majors ladder band is 1.13 on paper. Below 3.0 a fill is not a visible mark, so the
    matrix requires a 1px outline; without it the range is invisible in high-contrast and print."""
    assert contrast(tk.LADDER_BAND, PAPER) < 3.0, "the band tint is no longer a light fill"
    src = (PIPELINE / "build_majors_pages.py").read_text()
    band_rect = next(ln for ln in src.splitlines() if 'fill="{BAND}"' in ln)
    assert "stroke=" in band_rect or 'stroke="{FAINT}"' in src, (
        "the ladder band fill is lighter than 3:1 and needs a 1px outline"
    )
    assert contrast(tk.INK_FAINT, PAPER) >= 3.0, "the outline colour must itself be visible"


def test_charts_and_cards_carry_no_raw_palette_hex():
    """The premium bars shipped raw pre-forest gradient stops (#17936a, #c23522) and the gem pill
    three raw golds. Raw hex cannot follow the palette, which is how a rebrand leaves colour behind."""
    for name in ("build_college_pages.py", "build_majors_pages.py", "build_home_chart.py"):
        src = (PIPELINE / name).read_text()
        code = "\n".join(
            ln for ln in src.splitlines() if not ln.lstrip().startswith(("#", '"""', "*", "/*"))
        )
        for stale in STALE:
            assert stale not in code, f"{name} still hard-codes the pre-forest colour {stale}"


def test_social_cards_never_draw_over_their_footer():
    """A two-line headline plus a statistic pushed the caption to y=500; two 30px lines then ran to
    about 573, crossing the footer rule at 552. Around 1,817 college cards hit that combination, so
    the caption block now sizes itself against the rule. Rendered and measured, not reasoned about."""
    from PIL import Image

    from pipeline import og_images as og

    out = Path("/tmp/og_footer_guard.png")
    og.card(
        out,
        "College · does it pay off?",
        "Pennsylvania State University Main Campus",  # wraps to two lines
        big="421 of 489 pay off",
        sub=(
            "Programs whose graduates out-earn a typical Pennsylvania high-school graduate, "
            "measured a few years after finishing."
        ),
    )
    im = Image.open(out).convert("RGB")
    bg = im.getpixel((600, 5))
    rows = [
        y
        for y in range(200, og.FOOTER_RULE_Y)
        if any(im.getpixel((x, y)) != bg for x in range(og.MARGIN, og.W - og.MARGIN))
    ]
    lowest = max(rows)
    assert lowest < og.FOOTER_RULE_Y - 2, (
        f"card content reaches y={lowest}, colliding with the footer rule at {og.FOOTER_RULE_Y}"
    )


def test_embed_widget_is_generated_and_self_contained():
    """The embed renders inside other people's pages, so it cannot use site/styles.css. That meant
    a hand-copied :root, which is how it kept the ENTIRE old blue palette through the rebrand while
    every other surface moved. Its tokens are now generated by `make tokens`; self-contained must
    not mean hand-copied. It also loads no webfont on purpose: no request is spent on type in a
    third-party page, so --display falls through to Georgia."""
    html = (SITE / "embed" / "index.html").read_text()
    assert "@tokens:start" in html and "@tokens:end" in html, (
        "the embed :root must be generated, not hand-maintained"
    )
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    body = style.split("@tokens:end", 1)[1]
    stray = re.findall(r"#[0-9a-fA-F]{3,8}\b", body)
    assert not stray, f"the embed hard-codes colour outside its generated block: {stray}"
    literal_radii = re.findall(r"border-radius:\s*([0-9][^;]*);", body)
    assert not literal_radii, f"the embed hard-codes radii instead of --r-*: {literal_radii}"
    for remote in ("fonts.googleapis", "fonts.gstatic", "@font-face", "/fonts/"):
        assert remote not in html, f"the embed should not pull type into a host page ({remote})"


def test_no_hand_written_page_keeps_a_pre_forest_colour():
    """The same dead colours also sat in two hand-written pages, the embed widget's bar and the
    Compare gem pill, which no generator touches. A rebrand that only fixes generators leaves
    those behind, so they are checked directly. Generated trees are gitignored; skip what is absent."""
    for rel in ("embed/index.html", "compare/index.html", "index.html", "value-check/index.html"):
        page = SITE / rel
        if not page.exists():
            continue
        text = page.read_text()
        for stale in STALE:
            assert stale not in text, f"{rel} still ships the pre-forest colour {stale}"
