"""Build the program-table variants compared for the JavaScript-off decision (B or C).

Writes site/_measure/<variant>/index.html for one school (Penn State by default), all from the same
build code, so the only difference between them is how the program list is delivered:

  partial   today: 150 rows in the HTML, the rest in programs-tail.json (option A notice shown)
  full      option B: every row in the HTML, no tail
  full-cv   option B with content-visibility on each row, which only takes effect where rows are
            block boxes (the phone card layout); on the desktop table it is inert
  list      option C: a plain page with every row and no script

site/_measure/ is gitignored. Measure with:  node tests/compare_table_variants.js
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.build_canonical_profiles import (  # noqa: E402
    HEAD,
    PROGRAMS_CSV,
    canonical_page,
    programs_csv,
)
from pipeline.build_college_pages import FOOTER, esc, head, state_label  # noqa: E402
from pipeline.build_profile_pilot import _static_row, all_profiles  # noqa: E402

OUT = ROOT / "site" / "_measure"
PARQUET = ROOT / "published" / "value_check.parquet"
INSTITUTIONS = ROOT / "published" / "institutions.parquet"

CV_STYLE = (
    "  <style>@media (max-width: 767px) { .tw-table tbody tr { content-visibility: auto; "
    "contain-intrinsic-size: auto 220px; } }</style>\n"
)


def plain_list(meta: dict, rows: list[dict]) -> str:
    """Option C: every program in one static table, no script. noindex, canonical to the profile."""
    slug = meta["slug"]
    h = head(
        f"All programs at {meta['name']}",
        f"Every program the Department of Education lists for {meta['name']}.",
        f"https://truewise.dev/college/{slug}/",
    ).replace("<head>", '<head>\n  <meta name="robots" content="noindex" />', 1)
    h = h.replace("</head>", '  <link rel="stylesheet" href="/components.css" />\n</head>', 1)
    body = "".join(_static_row(r) for r in rows)
    return (
        h
        + '  <main class="wrap pg">\n'
        + f'    <nav class="crumbs"><a href="/college/{slug}/">{esc(meta["name"])}</a> &rsaquo; All programs</nav>\n'
        + f"    <h1>All {len(rows):,} programs at {esc(meta['name'])}</h1>\n"
        + f'    <p class="tw-source">Every program in ED&rsquo;s data for this school, {esc(state_label(meta["state"]))}. '
        + f'<a href="{PROGRAMS_CSV}" download>Download as CSV</a>.</p>\n'
        + '    <div class="tw-table__scroll" tabindex="0" role="region" aria-label="All programs"><table class="tw-table">'
        + f"<caption class='tw-table__caption'>All {len(rows):,} programs.</caption>"
        + f"<thead><tr>{HEAD}</tr></thead><tbody>{body}</tbody></table></div>\n"
        + "  </main>\n"
        + FOOTER
        + "</body>\n</html>\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unitid", default="214777")
    args = ap.parse_args()
    con = duckdb.connect()
    pmeta, rows = all_profiles(con, PARQUET)[args.unitid]
    city, bench = con.sql(
        f"SELECT i.city, max(v.earnings_threshold_state) FROM '{PARQUET}' v "
        f"LEFT JOIN '{INSTITUTIONS}' i USING (unitid) WHERE v.unitid = '{args.unitid}' GROUP BY 1"
    ).fetchone()
    import json

    slug = json.loads((ROOT / "published" / "slug_registry.json").read_text())[args.unitid]
    meta = {**pmeta, "city": city, "slug": slug, "in_institution_file": True}
    csv_text = programs_csv(con, PARQUET, [args.unitid])[args.unitid]

    variants = {}
    html, tail = canonical_page(meta, rows, slug, bench, 150)
    variants["partial"] = (html, tail)
    full, _ = canonical_page(meta, rows, slug, bench, 10**6)
    variants["full"] = (full, None)
    variants["full-cv"] = (full.replace("</head>", CV_STYLE + "</head>", 1), None)
    variants["list"] = (plain_list(meta, rows), None)

    for name, (page, tail_json) in variants.items():
        # Local measurement pages, never deployed; noindex keeps site-wide page checks off them.
        if "noindex" not in page:
            page = page.replace("<head>", '<head>\n  <meta name="robots" content="noindex" />', 1)
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page)
        (d / PROGRAMS_CSV).write_text(csv_text)
        if tail_json:
            (d / "programs-tail.json").write_text(tail_json)
        else:
            (d / "programs-tail.json").unlink(missing_ok=True)
    print(f"wrote {', '.join(variants)} for {meta['name']} ({len(rows)} programs) to {OUT}")


if __name__ == "__main__":
    main()
