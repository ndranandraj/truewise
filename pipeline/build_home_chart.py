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


def render_svg(counts: list[int], total: int, median: int) -> str:
    """A vertical histogram, 360x230 viewBox, scaling to its container width."""
    W, H = 360, 230
    x0, x1 = 8, 352  # plot horizontal bounds
    base_y = 176  # bars sit on this line
    top_y = 30  # tallest bar reaches here
    slot = (x1 - x0) / len(counts)
    bw = slot * 0.66
    mx = max(counts)
    pct = [round(100 * c / total) for c in counts]

    parts = [
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        'aria-labelledby="distTitle distDesc" style="max-width:380px;height:auto">',
        '<title id="distTitle">How far college programs out-earn a high-school graduate</title>',
        f'<desc id="distDesc">Of {total:,} judged programs, {counts[0]:,} (about {pct[0]}%) '
        f"leave graduates earning less than a typical high-school graduate; the rest earn more, "
        f"a median of {median}% more. Bars, left to right: "
        + "; ".join(f"{LABELS[i]} {counts[i]:,}" for i in range(len(counts)))
        + ".</desc>",
    ]
    # Bars.
    for i, c in enumerate(counts):
        h = round((base_y - top_y) * c / mx)
        x = round(x0 + i * slot + (slot - bw) / 2, 1)
        y = base_y - h
        fill = NEG if i == 0 else BAR
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bw:.1f}" height="{h}" rx="2" '
            f'fill="{fill}" data-count="{c}"/>'
        )
        parts.append(
            f'<text x="{x + bw / 2:.1f}" y="{y - 5}" text-anchor="middle" '
            f'font-size="10" font-weight="700" fill="{TEXT}">{pct[i]}%</text>'
        )
    # Baseline.
    parts.append(
        f'<line x1="{x0}" y1="{base_y}" x2="{x1}" y2="{base_y}" '
        f'stroke="{BASELINE}" stroke-width="1"/>'
    )
    # The high-school line: a marker between the "earn less" bar and the rest.
    hx = round(x0 + slot, 1)
    parts.append(
        f'<line x1="{hx}" y1="{top_y - 8}" x2="{hx}" y2="{base_y}" stroke="{NEG}" '
        f'stroke-width="1" stroke-dasharray="3 3"/>'
    )
    # Label sits to the LEFT of the line, over the empty space above the short "earn less" bar,
    # so it never collides with the tall bars to the right.
    parts.append(
        f'<text x="{hx - 5}" y="{top_y + 14}" text-anchor="end" font-size="9.5" fill="{TEXT}" '
        f'font-weight="700">HS line</text>'
    )
    # Axis captions.
    parts.append(
        f'<text x="{round(x0 + slot / 2, 1)}" y="{base_y + 18}" text-anchor="middle" '
        f'font-size="10" fill="{TEXT}" font-weight="600">earn less</text>'
    )
    parts.append(
        f'<text x="{round(x0 + slot * 4, 1)}" y="{base_y + 18}" text-anchor="middle" '
        f'font-size="10" fill="{TEXT_DIM}">earn more than a high-school graduate &#8594;</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def build_block(counts, total, median) -> str:
    svg = render_svg(counts, total, median)
    return (
        f"{START}\n"
        '          <p class="dots-label">What graduates earn vs a high-school grad</p>\n'
        f'          <figure class="home-dist">{svg}</figure>\n'
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
