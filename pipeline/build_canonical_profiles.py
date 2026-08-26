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

from pipeline.build_college_pages import (
    BASE,
    FOOTER,
    STATE_NAMES,
    _calculator,
    esc,
    head,
    money,
    slugify,
)
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


INSTITUTIONS = ROOT / "published" / "institutions.parquet"
NP_LABELS = ["Under $30k", "$30k to $48k", "$48k to $75k", "$75k to $110k", "$110k and up"]


def _benchmark(con, unitid: str):
    row = con.sql(
        f"SELECT max(earnings_threshold_state) AS t FROM '{PARQUET}' WHERE unitid = '{unitid}'"
    ).fetchone()
    return row[0] if row else None


def _net_price(con, unitid: str) -> dict | None:
    """This school's net price by income band, from institutions.parquet (same source as the live
    summary page). Returns None when the school reports no net price."""
    if not INSTITUTIONS.exists():
        return None
    row = con.sql(
        f"""SELECT net_price_avg, net_price_0_30k, net_price_30_48k, net_price_48_75k,
                   net_price_75_110k, net_price_110k_plus
            FROM '{INSTITUTIONS}' WHERE unitid = '{unitid}'"""
    ).fetchone()
    if not row:
        return None
    avg, *brackets = (None if v is None else round(float(v)) for v in row)
    if avg is None and not any(b is not None for b in brackets):
        return None
    return {"avg": avg, "brackets": brackets}


def canonical_page(
    meta: dict,
    rows: list[dict],
    slug: str,
    benchmark,
    threshold: int,
    net_price: dict | None = None,
) -> tuple[str, str | None]:
    name = meta["name"]
    st = meta["state"]
    st_name = STATE_NAMES.get(st, st)
    canonical = f"{BASE}/college/{slug}/"
    total = len(rows)
    decided = sum(1 for r in rows if r["verdict"] != "insufficient")
    passed = sum(1 for r in rows if r["verdict"] == "pass")
    fail = sum(1 for r in rows if r["verdict"] == "fail")
    # A 1-year figure is only ever DISPLAYED for an assessed row (horizon is None on insufficient
    # rows), so this is exactly "does the page show at least one 1-year earnings value".
    has_1yr = any(r.get("horizon") == "1yr_after_completion" for r in rows)
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
    # CollegeOrUniversity structured data (carried over from the retired summary page): it is the
    # entity search engines attach the profile to, so dropping it at the cutover would be a silent SEO
    # regression. Serialized through _island_json for the same '<'-escaping safety as the breadcrumb.
    college = {
        "@context": "https://schema.org",
        "@type": "CollegeOrUniversity",
        "name": name,
        "url": canonical,
    }
    if meta.get("city"):
        college["address"] = {
            "@type": "PostalAddress",
            "addressLocality": meta["city"],
            "addressRegion": st,
            "addressCountry": "US",
        }
    ld = (
        '  <link rel="stylesheet" href="/components.css" />\n'
        '  <script type="application/ld+json">\n  ' + _island_json(college) + "\n  </script>\n"
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
    loc = f"{esc(meta['city'])}, {esc(st_name)}" if meta.get("city") else esc(st_name)
    ctrl = f" &middot; {esc(meta['control'])}" if meta.get("control") else ""
    parts.append(f'    <p class="idline">{loc}{ctrl}</p>\n')
    parts.append(f'    <div class="verdict">{verdict}</div>\n')

    # B10 affordability: net price by income + the "what would this cost you" calculator, reusing the
    # live summary's calculator (income x years arithmetic on published net price). The static table
    # is the no-JS fallback.
    if net_price and (net_price.get("avg") is not None or any(net_price.get("brackets") or [])):
        brackets = list(net_price.get("brackets") or [None] * 5)
        # _calculator wants a programs list with payback + a flag; adapt from our verdict rows.
        calc_programs = [
            {
                "payback": r["payback"],
                "flag": "passes_earnings_premium" if r["verdict"] == "pass" else r["verdict"],
            }
            for r in rows
        ]
        parts.append('    <h2 class="sec">What would this cost you?</h2>\n')
        parts.append(_calculator(meta, net_price, brackets, NP_LABELS, calc_programs))
        parts.append(
            '    <div class="tscroll"><table class="t np"><thead><tr><th>Family income</th>'
            '<th class="num">Net price per year</th></tr></thead><tbody>\n'
        )
        for lab, b in zip(NP_LABELS, brackets, strict=False):
            if b is not None:
                parts.append(f'      <tr><td>{lab}</td><td class="num">{money(b)}</td></tr>\n')
        if net_price.get("avg") is not None:
            parts.append(
                f"      <tr><td><b>All families (average)</b></td>"
                f'<td class="num"><b>{money(net_price["avg"])}</b></td></tr>\n'
            )
        parts.append("    </tbody></table></div>\n")
        parts.append(
            '    <p class="tw-source">Net price is the yearly cost after grants and scholarships, by '
            "family income (College Scorecard). It reflects students who received federal aid.</p>\n"
        )

    parts.append('    <h2 class="sec">Program earnings vs a high-school graduate</h2>\n')
    # Mixed-window disclosure: when the page shows any 1-year earnings figure, state plainly that
    # 1-year and 4-year figures are not the same measurement and must not be compared as if they were.
    # This MUST sit OUTSIDE the .tw-profile-static mount: progressive enhancement replaces that mount's
    # innerHTML wholesale, so a notice placed inside it vanishes after JS runs. As a sibling above the
    # data-tw-profile container it survives enhancement, sorting, and "Show all".
    if has_1yr:
        parts.append(
            '    <p class="tw-source tw-window-note">Earnings are measured four years after '
            "completion when available. Where four-year earnings are suppressed, one-year earnings are "
            'shown and marked <span class="tw-oneyr">1-year earnings</span>. One-year and four-year '
            "figures reflect different career stages and should not be compared as if measured at the "
            "same time.</p>\n"
        )
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

    window_txt = (
        "measured four years after completion where available (programs shown with a 1-year figure are "
        "marked)"
        if has_1yr
        else "measured four years after completion"
    )
    parts.append(
        '    <p class="tw-source">Source: U.S. Department of Education College Scorecard, release '
        f"{SCORECARD_RELEASE}. Earnings are medians {window_txt}, compared with the "
        f"state high-school-graduate benchmark ({esc(bench_txt)}/yr). Debt is federal loans only. "
        "Suppressed values are shown as insufficient data, never imputed. Figures describe past "
        "graduates and are never a promise.</p>\n"
    )
    parts.append("  </main>\n")
    parts.append(FOOTER)
    # defer: these are progressive enhancement only (the static table is the baseline), so they must
    # never block first paint. The LCP element is the h1, so keeping JS off the critical path matters.
    parts.append('  <script defer src="/components/table.js"></script>\n')
    parts.append('  <script defer src="/components/profile.js"></script>\n')
    parts.append("</body>\n</html>\n")
    return "".join(parts), tail_json


def _cutover_diff(con, threshold: int) -> None:
    """Render, for each representative, the CURRENT summary page and the NEW canonical page side by
    side into staging/_cutover-diff/<slug>/, so the exact go-live content change can be reviewed
    before the cutover ships. Read-only: writes nothing to site/."""
    from pipeline.build_college_pages import (
        build_model,
        build_slugs,
        college_page,
        qualifying_schools,
    )

    schools, by_state, _ = build_model(con)
    qualified = qualifying_schools(schools)
    slugs = build_slugs(qualified)
    out = OUT / "_cutover-diff"
    print(f"{'case':18} {'slug':44} {'current rows':>12} {'canonical static':>16}")
    for case, unitid in REPS.items():
        if unitid not in qualified:
            continue
        s = qualified[unitid]
        slug = slugs[unitid]
        progs = by_state.get(s["state"], {}).get(unitid, [])
        current = college_page(s, progs, slug)
        meta, rows = _rows_for(con, unitid)
        canonical, _ = canonical_page(
            meta, rows, slug, _benchmark(con, unitid), threshold, _net_price(con, unitid)
        )
        d = out / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "current-summary.html").write_text(current)
        (d / "new-canonical.html").write_text(canonical)
        print(
            f"{case:18} {slug[:44]:44} {current.count('<tr'):>12} {min(threshold, len(rows)):>16}"
        )
    print(f"\nwrote current + canonical pairs to {out.relative_to(ROOT)}/ (review before cutover)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every profile-eligible school (slow)")
    ap.add_argument(
        "--school", help="one UNITID (ad-hoc, e.g. to inspect an all-insufficient school)"
    )
    ap.add_argument(
        "--cutover-diff",
        action="store_true",
        help="write CURRENT summary + NEW canonical per rep into staging/_cutover-diff/ to review",
    )
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = ap.parse_args()
    con = duckdb.connect()

    if args.cutover_diff:
        _cutover_diff(con, args.threshold)
        return

    if args.school:
        targets = [(None, args.school)]
    elif args.all:
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
        html, tail_json = canonical_page(
            meta, rows, slug, _benchmark(con, unitid), args.threshold, _net_price(con, unitid)
        )
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
