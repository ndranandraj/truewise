"""Per-page social share images (Open Graph cards).

Every page used to share the same generic og.png, so a nursing-salary link and a college profile
looked identical when posted to social, chat, or a group thread. This renders a branded 1200x630
card per page carrying its actual headline, which is the format parents and journalists forward.

Cards are PNGs because social scrapers (Facebook, iMessage, LinkedIn, Slack) do not reliably
render SVG as og:image. Fonts are bundled in the repo (Liberation Sans, SIL OFL) so the build does
not depend on whatever fonts a CI runner happens to have.

Scope for now: the homepage, the 292 major pages, and the findings pages, i.e. the pages most
likely to be shared. The card() function is generic, so per-college cards can be added later.

Usage:
    python -m pipeline.og_images
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.config import ROOT

# Site palette: generated from design/tokens.json so these can never drift from the CSS.
from pipeline.tokens_gen import (
    BAD,
    BG,
    BRAND,
    BRAND_DEEP,
    INK,
    INK_FAINT,
    INK_SOFT,
    LINE,
)

SITE = ROOT / "site"
OG_DIR = SITE / "og"
FONT_DIR = ROOT / "assets" / "fonts"

W, H = 1200, 630
MARGIN = 80

# Vertical budget for the caption block, so a card can never draw over its own footer.
FOOTER_RULE_Y = H - 78  # where the attribution rule is drawn
FOOTER_CLEARANCE = 18  # breathing room between the last caption line and that rule
SUB_ADVANCE = 40  # baseline-to-baseline for the 30px caption
SUB_INK = 38  # visual height of one caption line (30px font plus descender)

_BOLD = FONT_DIR / "LiberationSans-Bold.ttf"
_REG = FONT_DIR / "LiberationSans-Regular.ttf"


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_BOLD if bold else _REG), size)


def _wrap(draw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    """Greedy word-wrap to a pixel width, truncating with an ellipsis past max_lines."""
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    # If we ran out of lines with words remaining, mark the last line as truncated.
    if len(lines) == max_lines and draw.textlength(" ".join(words), font=font) > sum(
        draw.textlength(line + " ", font=font) for line in lines
    ):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def _wordmark(draw, x: int, y: int) -> None:
    f = _font(True, 40)
    draw.text((x, y), "true", font=f, fill=INK)
    draw.text((x + draw.textlength("true", font=f), y), "wise", font=f, fill=BRAND)


def card(
    out_path: Path,
    eyebrow: str,
    headline: str,
    big: str | None = None,
    big_color: str = BRAND_DEEP,
    sub: str | None = None,
) -> None:
    """Render one 1200x630 share card and write it as a PNG."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # A slim brand band down the left edge, and the wordmark top-left.
    d.rectangle([0, 0, 14, H], fill=BRAND)
    _wordmark(d, MARGIN, 64)
    d.text(
        (MARGIN + 190, 74),
        "Honest US education data",
        font=_font(False, 22),
        fill=INK_FAINT,
    )

    # Eyebrow.
    d.text(
        (MARGIN, 176),
        (eyebrow or "").upper(),
        font=_font(True, 24),
        fill=BRAND,
    )

    # Headline (up to two lines).
    hf = _font(True, 82)
    y = 214
    for line in _wrap(d, headline, hf, W - 2 * MARGIN, 2):
        d.text((MARGIN, y), line, font=hf, fill=INK)
        y += 92

    # Big statistic and its caption.
    #
    # The caption used to be given a flat two lines, which does not fit when the headline also
    # takes two. A two-line headline ends at 398, the statistic pushes the caption to 500, and two
    # 30px lines then run to about 570, crossing the footer rule at 552. Roughly 1,817 college
    # cards hit that combination. So the caption is allowed only as many lines as actually fit
    # above the rule: the type sizes stay put and a long caption ellipsizes instead of colliding.
    y = max(y + 12, 402)
    if big:
        bf = _font(True, 76)
        d.text((MARGIN, y), big, font=bf, fill=big_color)
        y += 90
    if sub:
        sf = _font(False, 30)
        room = (FOOTER_RULE_Y - FOOTER_CLEARANCE) - y
        max_lines = max(1, min(2, int((room + SUB_ADVANCE - SUB_INK) // SUB_ADVANCE)))
        for line in _wrap(d, sub, sf, W - 2 * MARGIN, max_lines):
            d.text((MARGIN, y), line, font=sf, fill=INK_SOFT)
            y += SUB_ADVANCE

    # Footer rule + attribution.
    d.line([MARGIN, FOOTER_RULE_Y, W - MARGIN, FOOTER_RULE_Y], fill=LINE, width=2)
    ff = _font(True, 26)
    d.text((MARGIN, H - 58), "truewise.dev", font=ff, fill=BRAND_DEEP)
    d.text(
        (MARGIN + d.textlength("truewise.dev", font=ff) + 14, H - 56),
        "· open U.S. Department of Education data",
        font=_font(False, 24),
        fill=INK_FAINT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # compress_level 6 (zlib default) is the speed/size knee; optimize=True triples render time
    # for ~3% smaller files, which does not pay off across the ~5,000 college cards built per deploy.
    img.save(out_path, "PNG", compress_level=6)


if __name__ == "__main__":
    # Rendered from the page builders; running standalone makes a couple of samples for review.
    # The review sample goes to staging/, which is gitignored and NOT deployed. It used to be
    # written into site/og/, so a development sample was publicly fetchable on every deploy.
    SAMPLE_DIR = ROOT / "staging" / "og-samples"
    OG_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    card(
        SAMPLE_DIR / "sample_major.png",
        "College major · median graduate earnings",
        "Nursing",
        big="$85,357",
        sub="Median salary a few years after graduating, across US programs.",
    )
    card(
        SITE / "og.png",
        "Open, honest US education data",
        "Does a college program pay off?",
        big="1 in 11",
        big_color=BAD,
        sub="college programs leave graduates earning less than a high-school graduate.",
    )
    print("wrote sample cards")
