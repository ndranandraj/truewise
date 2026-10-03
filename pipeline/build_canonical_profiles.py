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
    esc,
    head,
    known_state,
    slugify,
    state_label,
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
# Written beside index.html for every profile with more than CSV_MIN_PROGRAMS programs.
PROGRAMS_CSV = "programs.csv"
CSV_MIN_PROGRAMS = 150
# Live profiles send every program in the HTML (option B, 30 September 2026). Measured on Penn
# State, the largest (489 programs), under the site's phone conditions against the 150-row page:
# LCP 1,024 ms against 1,040, TBT 17 ms (150-row range 3 to 73), CLS 0; search, filter and sort
# 21, 10 and 18 ms; no long tasks scrolling all 489 rows with scripts blocked; 32 KB compressed.
# See truewise-review-noscript-programs-2026-09-27.md. The progressive tail stays in the code for
# a school that ever outgrows this, and the partial-table notice with it.
LIVE_STATIC_ROWS = 100_000
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


REPORT_URL = (
    "https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction"
    "&body=Page%20URL%3A%0AWhat%20looks%20wrong%3A%0AExpected%20value%20and%20source%3A"
)


def loc_text(meta: dict, st_name: str) -> str:
    return f"{meta['city']}, {st_name}" if meta.get("city") else st_name


def canonical_page(
    meta: dict,
    rows: list[dict],
    slug: str,
    benchmark,
    threshold: int,
    net_price: dict | None = None,
) -> tuple[str, str | None]:
    """The college profile (profile release, 30 September 2026: design plan Prototype B).

    Summary, cost, programs and sources, with the section links sticky on phones and the side rail
    from 1200px. Every figure in the summary counts undergraduate programs, as the site's headline
    does; graduate comparisons stay in the table, labelled."""
    from pipeline import profile_layout as pl

    name = meta["name"]
    st = meta["state"]
    st_name = state_label(st)
    canonical = f"{BASE}/college/{slug}/"
    total = len(rows)
    c = pl.counts(rows)
    decided = c["decided"]
    located = known_state(st)
    where = ", ".join(p for p in (meta.get("city"), st) if p) if located else ""
    at_where = f"{name} in {where}" if where else name
    of_state = f"{st_name} " if located else ""

    # The size clause separates the last colliding descriptions: same-named campuses differ in
    # programs reported or recent graduates, never a fabricated suffix (see git history).
    grads = sum(r.get("completers") or 0 for r in rows)
    size = f"Reports {total} program{'' if total == 1 else 's'}"
    if grads:
        size += f" and {int(grads):,} recent graduate{'' if grads == 1 else 's'}"
    size += "."

    # The description says what the summary box says: undergraduate programs where any have a
    # verdict, otherwise all programs, otherwise why there is no verdict.
    ug_c = pl.counts([r for r in rows if not r.get("grad")])
    hc, kind = (ug_c, "undergraduate programs") if ug_c["decided"] else (c, "programs")
    if hc["decided"] and hc["fail"]:
        desc = (
            f"At {at_where}, {hc['fail']} of {hc['decided']} assessed {kind} have graduates who "
            f"earn less than a typical {of_state}high-school graduate. {size} Program-by-program "
            "earnings, from federal data."
        )
    elif hc["decided"]:
        desc = (
            f"At {at_where}, all {hc['decided']} assessed {kind} have graduates out-earning a "
            f"typical {of_state}high-school graduate. {size} Program earnings, from federal data."
        )
    elif c["nobench"]:
        desc = (
            f"At {at_where}, the Department of Education reports earnings for {c['nobench']} "
            f"program{'' if c['nobench'] == 1 else 's'}, with no state benchmark to compare them "
            f"with. {size} From federal data."
        )
    elif c["none"] < total:
        desc = (
            f"At {at_where}, the Department of Education publishes no graduate earnings for any "
            f"program, so none can be assessed. {size} From federal data."
        )
    else:
        desc = (
            f"The Department of Education lists programs at {at_where} but reports no figures "
            f"for them. {size}"
        )

    # Title carries the place, always (86 title values were once shared by 202 pages).
    title = (
        f"{name}, {where}: cost and graduate earnings"
        if where
        else (f"{name}: cost and graduate earnings")
    )
    # Serialized through _island_json (escapes '<') so a name cannot break out of the script.
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
    page_head = head(title, desc, canonical, ld, og_image=f"/og/college/{slug}.png").replace(
        "</head>",
        '  <link rel="stylesheet" href="/article.css" />\n'
        '  <link rel="stylesheet" href="/profile.css" />\n</head>',
        1,
    )

    # The program table: static rows, a JSON island of the same rows, and a tail only if a school
    # ever outgrows the threshold (live profiles send every row since 30 September).
    intro, caption = pl.program_intro(benchmark, of_state)
    static_rows = rows[:threshold]
    tail = rows[threshold:]
    body_rows = "".join(_static_row(r) for r in static_rows)
    tail_json = _island_json({"programs": tail}) if tail else None
    island = _island_json(
        {
            "rows": static_rows,
            "coverage": {"measured": decided, "total": total},
            "caption": caption,
        }
    )
    profile_attrs = (
        f'data-tw-profile data-tail="programs-tail.json" data-remaining="{len(tail)}"'
        if tail
        else "data-tw-profile"
    )
    cov_pct = round(100 * decided / total) if total else 0
    table = [f"      <div {profile_attrs}>\n"]
    table.append(
        f'        <script type="application/json" class="tw-profile-data">{island}</script>\n'
    )
    table.append('        <div class="tw-profile-static">\n')
    table.append(
        f'          <p class="tw-coverage"><b>{decided} of {total}</b> programs could be assessed '
        f'<span class="tw-coverage__note">{cov_pct}% have an earnings verdict</span></p>\n'
    )
    # A partial table must say so above the rows, in the initial HTML, inside the mount so it is
    # replaced only when ProgramTable renders the live count (option A, 29 September).
    if tail:
        table.append(
            f'          <p class="tw-partial" data-tw-partial>Summary figures cover all {total:,} '
            f"programs. This table shows the first {len(static_rows):,}. "
            f'<a href="{PROGRAMS_CSV}" download>Download all {total:,} programs (CSV)</a>.</p>\n'
        )
    table.append(
        '          <div class="tw-table__scroll" tabindex="0" role="region" aria-label="Programs and earnings"><table class="tw-table">'
        f'<caption class="tw-table__caption">{esc(caption)}</caption>'
        f"<thead><tr>{HEAD}</tr></thead><tbody>{body_rows}</tbody></table></div>\n"
    )
    table.append("        </div>\n      </div>\n")
    if tail or total > CSV_MIN_PROGRAMS:
        # Outside the mount, so the complete list stays one click away after the table enhances.
        table.append(
            f'      <p class="tw-source">Every program, including those without a verdict: '
            f'<a href="{PROGRAMS_CSV}" download>download all {total:,} (CSV)</a>.</p>\n'
        )

    chips = "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in pl.NAV)
    loc = ", ".join(p for p in (meta.get("city"), st_name) if p)
    ctrl = f" &middot; {esc(meta['control'])}" if meta.get("control") else ""
    parts = [
        page_head,
        '  <main class="wrap art prof has-rail">\n',
        pl.rail(meta, c, net_price),
        f'    <nav class="crumbs"><a href="/colleges/">Colleges</a> &rsaquo; '
        f'<a href="/colleges/{st.lower()}/">{esc(st_name)}</a> &rsaquo; {esc(name)}</nav>\n',
        f"    <h1>{esc(name)}</h1>\n",
        f'    <p class="idline">{esc(loc)}{ctrl}</p>\n',
        pl.summary(meta, rows, benchmark, net_price),
        f'    <nav class="sectnav" aria-label="Sections"><p class="sectnav__label" id="sn-l">'
        f"{len(pl.NAV)} sections</p>"
        f'<div class="sectnav__scroll"><ul aria-labelledby="sn-l">{chips}</ul></div></nav>\n',
        pl.cost_section(meta, rows, net_price),
        '    <section id="programs" aria-labelledby="programs-h" class="progs">\n',
        '      <h2 id="programs-h">Program earnings</h2>\n',
        f"      <p>{intro}</p>\n",
        pl.program_notes(meta, c),
        *table,
        "    </section>\n",
        pl.sources_section(meta, benchmark),
        "  </main>\n",
        FOOTER,
        # defer: progressive enhancement only; the static table is the baseline.
        '  <script defer src="/components/table.js"></script>\n',
        '  <script defer src="/components/profile.js"></script>\n',
        "</body>\n</html>\n",
    ]
    return "".join(parts), tail_json


# The status of each program in the CSV. Kept apart deliberately: a program ED reports without
# earnings, one it lists with no figures at all, and one with earnings but no benchmark are three
# different facts, and none of them is a judgement of the program.
CSV_STATUS = {
    "pass": "above the state high-school line",
    "fail": "below the state high-school line",
    "no_benchmark": "earnings published, no state high-school benchmark to compare with",
    "earnings_not_published": "program reported, earnings not published",
    "nothing_reported": "program listed, no figures reported",
}
CSV_COLUMNS = [
    "unitid",
    "opeid6",
    "institution",
    "cip_code",
    "cip_title",
    "program",
    "credential_level",
    "credential",
    "graduate_program",
    "status",
    "status_meaning",
    "earnings_median",
    "earnings_window",
    "state_hs_line",
    "gap_vs_hs_line",
    "debt_median",
    "debt_as_years_of_gain",
    "graduates",
    "campuses_sharing_these_figures",
    "source",
]


def _csv_status(r) -> str:
    flag = r["value_flag"]
    if flag == "passes_earnings_premium":
        return "pass"
    if flag == "fails_earnings_premium":
        return "fail"
    if r["earnings"] is not None:
        return "no_benchmark"
    if r["completers_count"] is None and r["debt_median"] is None:
        return "nothing_reported"
    return "earnings_not_published"


def programs_csv(con, parquet, unitids) -> dict[str, str]:
    """{unitid: CSV text} of every program ED lists for each school, from the complete dataset.

    One row per UNITID x CIP x credential level (unique for every profiled school), including
    programs without a verdict. The earnings window is stated whenever an earnings figure is."""
    import csv
    import io

    from pipeline.build_profile_pilot import GRAD_LEVELS, _row_from

    ids = ", ".join(f"'{u}'" for u in unitids)
    have = {r[0] for r in con.sql(f"DESCRIBE SELECT * FROM '{parquet}'").fetchall()}
    grp = "coalesce(opeid6, unitid)" if "opeid6" in have else "unitid"
    rows = con.sql(
        f"""SELECT *, count(*) OVER (PARTITION BY {grp}, cip_code, credential_level) AS n_campuses
            FROM '{parquet}' WHERE TRY_CAST(unitid AS BIGINT) IS NOT NULL"""
    ).df()
    rows = rows[rows["unitid"].isin(list(unitids))] if ids else rows.iloc[0:0]
    rows = rows.astype(object).where(rows.notna(), None)
    rows = rows.sort_values(["unitid", "cip_code", "credential_level"])
    out: dict[str, io.StringIO] = {}
    for rec in rows.to_dict("records"):
        buf = out.get(rec["unitid"])
        if buf is None:
            buf = out[rec["unitid"]] = io.StringIO()
            csv.writer(buf, lineterminator="\n").writerow(CSV_COLUMNS)
        status = _csv_status(rec)
        shown = status in ("pass", "fail", "no_benchmark")
        page_row = _row_from(rec)
        horizon = {
            "4yr_after_completion": "4 years after completion",
            "1yr_after_completion": "1 year after completion",
        }.get(rec.get("earnings_horizon") or "", "")

        def num(v):
            return "" if v is None else (int(v) if float(v).is_integer() else round(float(v), 1))

        csv.writer(buf, lineterminator="\n").writerow(
            [
                rec["unitid"],
                rec.get("opeid6") or "",
                rec["inst_name"],
                rec["cip_code"],
                (rec["cip_desc"] or "").rstrip("."),
                page_row["program"],
                rec["credential_level"],
                rec["credential_desc"],
                "yes" if str(rec["credential_level"]) in GRAD_LEVELS else "no",
                status,
                CSV_STATUS[status],
                num(rec["earnings"]) if shown else "",
                horizon if shown else "",
                num(rec.get("earnings_threshold_state")),
                num(rec["earnings_premium_state"]) if status in ("pass", "fail") else "",
                num(rec["debt_median"]),
                num(rec["debt_payback_years"]) if status in ("pass", "fail") else "",
                num(rec["completers_count"]),
                int(rec["n_campuses"]),
                f"U.S. Department of Education, College Scorecard, release {SCORECARD_RELEASE}",
            ]
        )
    return {u: b.getvalue() for u, b in out.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every profile-eligible school (slow)")
    ap.add_argument(
        "--school", help="one UNITID (ad-hoc, e.g. to inspect an all-insufficient school)"
    )
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = ap.parse_args()
    con = duckdb.connect()

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
