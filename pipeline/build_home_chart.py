"""Homepage distribution chart: how far program graduates out-earn a high-school graduate.

All three independent reviews (2026-08-13) flagged the same gap: for a product whose whole
premise is comparison against a benchmark, there was no chart anywhere, only the 1-in-11 dot
motif. This renders the actual distribution: every judged program bucketed by how much more (or
less) its graduates earn than a typical high-school graduate in their state, with the "earn
less" bucket (~1 in 11) drawn in clay, the one colour the system reserves for a negative.

It is a build-time inline SVG, not a JS chart: no library (the homepage CSP allows no third-party
scripts), no layout shift, works with JavaScript disabled, and the bars are real <rect>s a
screen reader can reach through the <title>/<desc>. The counts come from the committed parquet,
so a test can pin them and they cannot drift from the data.

Usage:
    python -m pipeline.build_home_chart        # recompute + inject into site/index.html
"""

from __future__ import annotations

import re

import duckdb

from pipeline.config import ROOT
from pipeline.tokens_gen import HOME_BAR as BAR  # light brand tint for the "earn more" bars
from pipeline.tokens_gen import HOME_TEXT as TEXT
from pipeline.tokens_gen import HOME_TEXT_DIM as TEXT_DIM
from pipeline.tokens_gen import SERIES_NEG_ON_DARK as NEG

# Palette generated from design/tokens.json, tuned for the deep-forest finding band this sits on.
#
# NEG is the "earn less" bar and the high-school marker. Clay is the only negative in the design
# system, but true clay (--series-neg) is 1.89 on that band, well under the 3.0 a graphical mark
# needs, so the dark-band variant is used instead. It is 3.61: enough for a MARK, not for TEXT
# (4.5), which is why the "earn less" and "HS line" labels stay on TEXT (sand, 9.82) rather than
# being tinted to match the bar. The meaning is carried by those words, never by the fill alone.

SITE = ROOT / "site"
PARQUET = SITE.parent / "published" / "value_check.parquet"
INDEX = SITE / "index.html"

START = "<!-- HOME_CHART_START -->"
END = "<!-- HOME_CHART_END -->"

# Bucket edges on the earnings premium as a share of the state high-school-graduate benchmark
# (premium / threshold). The first bucket is everything below the line: graduates who earn less
# than a high-school graduate. Labels avoid em-dashes per house style.
EDGES = [-1e9, 0, 25, 50, 75, 100, 150, 1e9]
LABELS = [
    "earn less",
    "0-25% more",
    "25-50% more",
    "50-75% more",
    "75-100% more",
    "100-150% more",
    "150%+ more",
]

BASELINE = "rgba(255,255,255,.28)"


def compute_bins() -> tuple[list[int], int, int, float]:
    """Return (counts per bucket, total decided, fall-short count, median premium %)."""
    con = duckdb.connect()
    con.execute(f"CREATE VIEW v AS SELECT * FROM read_parquet('{PARQUET}')")
    case = "CASE\n"
    for i in range(len(LABELS)):
        lo, hi = EDGES[i], EDGES[i + 1]
        case += f"  WHEN pct >= {lo} AND pct < {hi} THEN {i}\n"
    case += "END"
    rows = con.execute(
        f"""
        WITH d AS (
          SELECT earnings_premium_state * 100.0 / earnings_threshold_state AS pct
          FROM v
          WHERE value_flag IN ('passes_earnings_premium','fails_earnings_premium')
            AND earnings_threshold_state IS NOT NULL
        )
        SELECT {case} AS b, count(*) FROM d GROUP BY b ORDER BY b
        """
    ).fetchall()
    counts = [0] * len(LABELS)
    for b, n in rows:
        counts[b] = n
    total = sum(counts)
    median = con.execute(
        """
        SELECT median(earnings_premium_state * 100.0 / earnings_threshold_state)
        FROM v WHERE value_flag IN ('passes_earnings_premium','fails_earnings_premium')
          AND earnings_threshold_state IS NOT NULL
        """
    ).fetchone()[0]
    return counts, total, counts[0], round(median)


def render_svg(
    counts: list[int],
    total: int,
    median: int,
    *,
    W: int = 480,
    BAR_W: int = 42,
    GAP: int = 14,
    caption_right: str = "earn more than a high-school graduate &#8594;",
    ids: str = "",
) -> str:
    """A vertical histogram. Defaults are the approved 480x260 desktop geometry.

    Bars are 42 wide with a 14 gap and labels are 13px, per the rebrand plan. The earlier 360x230
    chart put 9.5px system-font labels on 32px bars, which is below the 12px floor the design
    record sets for mono metadata. Width is symmetric by construction: seven 42px bars and six
    14px gaps is 378, leaving 51 either side of 480.

    The size is parameterised because font-size inside an SVG is in USER units: it is scaled by
    the viewBox transform along with everything else. A 480-wide viewBox rendered into a 335px
    phone column is scaled by 0.70, so nominal 13px labels land at about 9.1px and the readability
    problem this geometry was meant to fix comes straight back. No CSS unit escapes that transform,
    so the only honest fix is a second, narrower chart for narrow columns, which build_block emits
    alongside this one and CSS swaps at the breakpoint.
    """
    H = 260
    n = len(counts)

    def place(x: int, anchor: str, label: str, size: int = 13) -> tuple[int, str]:
        """Keep a label inside the viewBox, falling back to edge alignment.

        IBM Plex Mono advances 0.6em, so a label's width is predictable. The narrow variant is
        tight enough that a centred "earn less" and an end-anchored "HS line" both hang off the
        left edge; rather than hand-tuning each geometry, any label that would overflow is
        re-anchored to the nearer edge.
        """
        w = len(re.sub(r"&#\d+;", "-", label)) * size * 0.6
        lo = x - w / 2 if anchor == "middle" else (x - w if anchor == "end" else x)
        if lo < 2:
            return 2, "start"
        if lo + w > W - 2:
            return W - 2, "end"
        return x, anchor

    x0 = round((W - (n * BAR_W + (n - 1) * GAP)) / 2)  # 51
    slot = BAR_W + GAP
    base_y = 190  # bars sit on this line
    top_y = 40  # tallest bar reaches here
    bw = BAR_W
    mx = max(counts)
    pct = [round(100 * c / total) for c in counts]

    parts = [
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        f'aria-labelledby="distTitle{ids} distDesc{ids}" style="max-width:{W}px;height:auto">',
        f'<title id="distTitle{ids}">How far college programs out-earn a high-school '
        "graduate</title>",
        f'<desc id="distDesc{ids}">Of {total:,} judged programs, {counts[0]:,} (about {pct[0]}%) '
        f"leave graduates earning less than a typical high-school graduate; the rest earn more, "
        f"a median of {median}% more. Bars, left to right: "
        + "; ".join(f"{LABELS[i]} {counts[i]:,}" for i in range(len(counts)))
        + ".</desc>",
    ]
    # Bars.
    for i, c in enumerate(counts):
        h = round((base_y - top_y) * c / mx)
        x = x0 + i * slot
        y = base_y - h
        fill = NEG if i == 0 else BAR
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{h}" rx="2" '
            f'fill="{fill}" data-count="{c}"/>'
        )
        parts.append(
            f'<text x="{x + bw // 2}" y="{y - 8}" text-anchor="middle" '
            f'font-size="13" font-weight="600" fill="{TEXT}">{pct[i]}%</text>'
        )
    # Baseline.
    parts.append(
        f'<line x1="{x0}" y1="{base_y}" x2="{x0 + n * slot - GAP}" y2="{base_y}" '
        f'stroke="{BASELINE}" stroke-width="1"/>'
    )
    # The high-school line: a marker in the gap between the "earn less" bar and the rest.
    hx = x0 + BAR_W + GAP // 2
    parts.append(
        f'<line x1="{hx}" y1="{top_y - 10}" x2="{hx}" y2="{base_y}" stroke="{NEG}" '
        f'stroke-width="1" stroke-dasharray="3 3"/>'
    )
    # Label sits to the LEFT of the line, over the empty space above the short "earn less" bar,
    # so it never collides with the tall bars to the right.
    hsx, hsa = place(hx - 6, "end", "HS line")
    parts.append(
        f'<text x="{hsx}" y="{top_y + 4}" text-anchor="{hsa}" font-size="13" fill="{TEXT}" '
        f'font-weight="600">HS line</text>'
    )
    # Axis captions.
    elx, ela = place(x0 + BAR_W // 2, "middle", "earn less")
    parts.append(
        f'<text x="{elx}" y="{base_y + 22}" text-anchor="{ela}" '
        f'font-size="13" fill="{TEXT}" font-weight="600">earn less</text>'
    )
    # Right-aligned to the plot edge. At 13px mono the two captions would otherwise meet around
    # x=107, since "earn less" centred under the first bar already reaches it.
    erx, era = place(x0 + n * slot - GAP, "end", caption_right)
    parts.append(
        f'<text x="{erx}" y="{base_y + 22}" text-anchor="{era}" font-size="13" '
        f'fill="{TEXT_DIM}">{caption_right}</text>'
    )
    # Provenance, on the face of the chart rather than only in the description: a reader should be
    # able to see what the percentages are a share of without opening the accessibility text.
    parts.append(
        f'<text x="{x0}" y="{H - 12}" font-size="13" fill="{TEXT_DIM}">'
        f"n = {total:,} judged programs</text>"
    )
    parts.append("</svg>")
    return "".join(parts)


def build_block(counts, total, median) -> str:
    """Both chart variants, one shown at a time by CSS.

    A single SVG cannot hold 13px labels at every width, because its text scales with the viewBox
    (see render_svg). So the wide chart carries the approved desktop geometry, and a narrow one
    sized for a phone column renders at roughly 1:1 there, keeping the labels at their real size.
    The narrow variant shortens the right-hand caption, which does not fit at that width.

    Only one is exposed to assistive tech at a time: the hidden variant is aria-hidden, so the
    description is not announced twice.
    """
    wide = render_svg(counts, total, median)
    narrow = render_svg(
        counts,
        total,
        median,
        W=300,
        BAR_W=30,
        GAP=11,
        caption_right="earn more &#8594;",
        ids="M",
    )
    return (
        f"{START}\n"
        '          <p class="dots-label">What graduates earn vs a high-school grad</p>\n'
        f'          <figure class="home-dist home-dist--wide">{wide}</figure>\n'
        f'          <figure class="home-dist home-dist--narrow" aria-hidden="true">{narrow}</figure>\n'
        f"          {END}"
    )


def main() -> None:
    counts, total, fall_short, median = compute_bins()
    html = INDEX.read_text()
    if START not in html or END not in html:
        raise SystemExit("index.html is missing the HOME_CHART markers")
    pre, rest = html.split(START, 1)
    _, post = rest.split(END, 1)
    INDEX.write_text(pre + build_block(counts, total, median) + post)
    print(
        f"home chart: {total:,} judged, {fall_short:,} earn less "
        f"({round(100 * fall_short / total)}%), median +{median}%"
    )


if __name__ == "__main__":
    main()
