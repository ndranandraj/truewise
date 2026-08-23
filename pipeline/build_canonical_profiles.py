"""Stage 4.3b: the real canonical /college/<slug>/ profile generator (STAGED, not yet live).

Renders the full canonical profile using the validated delivery model (static core + JSON island +
progressive tail, threshold 150) wrapped in the real site chrome from build_college_pages. Carries the
three pilot-review fixes: HTML escaping, assessed-first program selection, and the "could be assessed"
coverage label. It states the benchmark dollar value and a dated source line (both flagged missing in
the pilot).

Output goes to staging/college/<slug>/ (git-ignored), NOT site/college/. Making /college/ the full
profile is the Stage 5 coordinated cutover; this builds and proves the generator without touching the
live summary pages. Uses the current palette via the semantic token bridge, so it is not a restyle.

Usage:
    python -m pipeline.build_canonical_profiles            # 4 representative schools -> staging/
    python -m pipeline.build_canonical_profiles --all       # every profile-eligible school
"""

from __future__ import annotations

import argparse

import duckdb

from pipeline.build_college_pages import BASE, FOOTER, STATE_NAMES, esc, head, money, slugify
from pipeline.build_profile_pilot import (
    DEFAULT_THRESHOLD,
    HEAD,
    REPS,
    _island_json,
    _rows_for,
    _static_row,
)
from pipeline.config import ROOT

PARQUET = ROOT / "published" / "value_check.parquet"
OUT = ROOT / "staging"
# College Scorecard release the value_check parquet was built from (matches the live source line).
SCORECARD_RELEASE = "2026-06-10"


def _benchmark(con, unitid: str):
    row = con.sql(
        f"SELECT max(earnings_threshold_state) AS t FROM '{PARQUET}' WHERE unitid = '{unitid}'"
    ).fetchone()
    return row[0] if row else None


def canonical_page(
    meta: dict, rows: list[dict], slug: str, benchmark, threshold: int
) -> tuple[str, str | None]:
    name = meta["name"]
    st = meta["state"]
    st_name = STATE_NAMES.get(st, st)
    canonical = f"{BASE}/college/{slug}/"
    total = len(rows)
    decided = sum(1 for r in rows if r["verdict"] != "insufficient")
    passed = sum(1 for r in rows if r["verdict"] == "pass")
    fail = sum(1 for r in rows if r["verdict"] == "fail")
    bench_txt = money(benchmark) if benchmark is not None else "a typical high-school graduate"

    # Honest headline + meta description carrying real numbers.
    if decided and fail:
        desc = (
            f"At {name}, {fail} of {decided} assessed programs leave graduates earning less than a "
            f"typical {st_name} high-school graduate. Program-by-program earnings, from federal data."
        )
        verdict = (
            f"Of <b>{decided}</b> assessed programs, <b>{passed}</b> leave graduates out-earning a "
            f"typical {esc(st_name)} high-school graduate (about {esc(bench_txt)}/yr) and "
            f"<b>{fail}</b> fall short. Another <b>{total - decided}</b> could not be assessed."
        )
    elif decided:
        desc = (
            f"At {name}, all {decided} assessed programs leave graduates out-earning a typical "
            f"{st_name} high-school graduate. Program earnings, from federal data."
        )
        verdict = (
            f"All <b>{decided}</b> assessed programs leave graduates out-earning a typical "
            f"{esc(st_name)} high-school graduate (about {esc(bench_txt)}/yr). "
            f"Another <b>{total - decided}</b> could not be assessed."
        )
    else:
        desc = f"At {name}, no programs have enough data for an earnings verdict yet. From federal data."
        verdict = (
            f"None of {esc(name)}'s <b>{total}</b> programs have enough data for an earnings verdict "
            "yet. Truewise shows what the federal data supports and nothing more."
        )

    title = f"{name}: what families pay and what graduates earn"
    # The breadcrumb is serialized through _island_json (escapes '<' as <) so a school name
    # containing '<' or '</script>' cannot break out of the ld+json <script> element.
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Colleges", "item": f"{BASE}/colleges/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": st_name,
                "item": f"{BASE}/colleges/{st.lower()}/",
            },
            {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
        ],
    }
    ld = (
        '  <link rel="stylesheet" href="/components.css" />\n'
        '  <script type="application/ld+json">\n  ' + _island_json(breadcrumb) + "\n  </script>\n"
    )

    static_rows = rows[:threshold]
    tail = rows[threshold:]
    body_rows = "".join(_static_row(r) for r in static_rows)
    tail_json = _island_json({"programs": tail}) if tail else None
    island = _island_json(
        {
            "rows": static_rows,
            "coverage": {"measured": decided, "total": total},
            "caption": f"Programs by earnings versus a typical {st_name} high-school graduate.",
        }
    )
    profile_attrs = (
        f'data-tw-profile data-tail="programs-tail.json" data-remaining="{len(tail)}"'
        if tail
        else "data-tw-profile"
    )
    cov_pct = round(100 * decided / total) if total else 0

    parts = [head(title, desc, canonical, ld, og_image=f"/og/college/{slug}.png")]
    parts.append('  <main class="wrap pg">\n')
    parts.append(
        f'    <nav class="crumbs"><a href="/colleges/">Colleges</a> &rsaquo; '
        f'<a href="/colleges/{st.lower()}/">{esc(st_name)}</a> &rsaquo; {esc(name)}</nav>\n'
    )
    parts.append(f"    <h1>{esc(name)}</h1>\n")
    parts.append(
        f'    <p class="idline">{esc(st_name)}{" &middot; " + esc(meta["control"]) if meta.get("control") else ""}</p>\n'
    )
    parts.append(f'    <div class="verdict">{verdict}</div>\n')

    # The canonical program table: static core + island + progressive tail, honest coverage label.
    parts.append(f"    <div {profile_attrs}>\n")
    parts.append(
        f'      <script type="application/json" class="tw-profile-data">{island}</script>\n'
    )
    parts.append('      <div class="tw-profile-static">\n')
    parts.append(
        f'        <p class="tw-coverage"><b>{decided} of {total}</b> programs could be assessed '
        f'<span class="tw-coverage__note">{cov_pct}% have an earnings verdict</span></p>\n'
    )
    parts.append('        <div class="tw-table__scroll"><table class="tw-table">')
    parts.append(
        f'<caption class="tw-table__caption">Programs by earnings versus a typical {esc(st_name)} '
        "high-school graduate.</caption>"
    )
    parts.append(f"<thead><tr>{HEAD}</tr></thead><tbody>{body_rows}</tbody></table></div>\n")
    parts.append("      </div>\n    </div>\n")

    parts.append(
        '    <p class="tw-source">Source: U.S. Department of Education College Scorecard, release '
        f"{SCORECARD_RELEASE}. Earnings are medians for graduates several years out, compared with the "
        f"state high-school-graduate benchmark ({esc(bench_txt)}/yr). Debt is federal loans only. "
        "Suppressed values are shown as insufficient data, never imputed. Figures describe past "
        "graduates and are never a promise.</p>\n"
    )
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append('  <script src="/components/table.js"></script>\n')
    parts.append('  <script src="/components/profile.js"></script>\n')
    parts.append("</body>\n</html>\n")
    return "".join(parts), tail_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every profile-eligible school (slow)")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = ap.parse_args()
    con = duckdb.connect()

    if args.all:
        from pipeline.build_college_pages import build_model, build_slugs, qualifying_schools

        qualified = qualifying_schools(build_model(con)[0])
        slugs = build_slugs(qualified)
        targets = [(slugs[u], u) for u in qualified]
    else:
        targets = [(None, u) for u in REPS.values()]

    n = 0
    for slug, unitid in targets:
        meta, rows = _rows_for(con, unitid)
        slug = slug or slugify(meta["name"])
        html, tail_json = canonical_page(meta, rows, slug, _benchmark(con, unitid), args.threshold)
        d = OUT / "college" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html)
        if tail_json:
            (d / "programs-tail.json").write_text(tail_json)
        n += 1
    print(
        f"canonical profiles: wrote {n} to {OUT.relative_to(ROOT)}/college/ (STAGED, not deployed)"
    )


if __name__ == "__main__":
    main()
