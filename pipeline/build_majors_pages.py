"""Generate static, crawlable pages per major (field of study): /majors/<slug>/.

Targets "what does a <major> degree pay" searches. Each page bakes: median earnings by
degree level (the degree ladder), the typical range across schools, the Value Check pass
rate, and the BLS job outlook (occupations, projected growth, annual openings) when present.
Then it links to the interactive Careers browser.

Reuses build_careers.build_fields, so every major page shows the same numbers as the app.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_majors_pages
"""

from __future__ import annotations

from collections import defaultdict

import duckdb

from pipeline.build_careers import build_fields
from pipeline.build_college_pages import BASE, BEACON, FOOTER, esc, head, money, slugify
from pipeline.cip_names import has_plain_name, plain_name, short_label, tidy_official
from pipeline.config import ROOT
from pipeline.og_images import card as render_card

SITE = ROOT / "site"

# Order the degree ladder from shortest credential to longest.
CRED_ORDER = {
    "Undergraduate Certificate or Diploma": 0,
    "Associate's Degree": 1,
    "Bachelor's Degree": 2,
    "Post-baccalaureate Certificate": 3,
    "Graduate/Professional Certificate": 4,
    "Master's Degree": 5,
    "Doctoral Degree": 6,
    "First Professional Degree": 7,
}


def _json(s) -> str:
    import json as _j

    return _j.dumps(s if s is not None else "")


def _headline(creds) -> dict:
    """Representative row for the headline: prefer Bachelor's, else the most-reported."""
    for c in creds:
        if c["credential"] == "Bachelor's Degree":
            return c
    return max(creds, key=lambda c: c.get("programs") or 0)


def major_page(cip, name, family, creds, slug) -> str:
    canonical = f"{BASE}/majors/{slug}/"
    head_row = _headline(creds)
    lead_earn = money(head_row["med"])
    lead_cred = head_row["cred_short"]
    # Speak the visitor's language in the title and headings, keep the federal label as
    # provenance. The slug is deliberately still built from the official name, so existing
    # indexed URLs do not move.
    plain = plain_name(cip, name)
    official = tidy_official(name)
    show_official = has_plain_name(cip) and official.lower() != plain.lower()
    # The figure and the year are what earn the click in a search result.
    # Keep this near 60 characters so search results do not truncate it. The credential lives in
    # the description and on the page; the figure and the year are what earn the click.
    title = f"{short_label(cip, name)} degree salary: {lead_earn} median (2026 federal data)"
    desc = (
        f"{plain} graduates typically earn about {lead_earn} ({lead_cred}). See median earnings by "
        f"degree level, the range across schools, and the job outlook. From federal data."
    )
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Majors","item":"{BASE}/majors/"}},
    {{"@type":"ListItem","position":2,"name":{_json(plain)},"item":"{canonical}"}}
  ]}}
  </script>
"""
    # A share card carrying this field's real figure, so a posted link is not a generic card.
    og_path = SITE / "og" / "majors" / f"{slug}.png"
    render_card(
        og_path,
        "College major · median graduate earnings",
        short_label(cip, name),
        big=lead_earn,
        sub="Median salary a few years after graduating, across US programs.",
    )
    parts = [head(title, desc, canonical, ld, og_image=f"/og/majors/{slug}.png")]
    parts.append('  <main class="wrap pg">\n')
    parts.append(
        f'    <nav class="crumbs"><a href="/majors/">Majors</a> &rsaquo; {esc(plain)}</nav>\n'
    )
    parts.append(f"    <h1>{esc(plain)}</h1>\n")
    idline = esc(family)
    if show_official:
        idline += f' &middot; federal classification: <span class="offname">{esc(official)}</span>'
    parts.append(f'    <p class="idline">{idline}</p>\n')
    parts.append(
        f'    <div class="verdict">{esc(plain)} graduates with a {esc(lead_cred.lower())} typically '
        f"earned about <b>{lead_earn}</b>, measured a few years after finishing (median across US "
        f"programs, College Scorecard).</div>\n"
    )
    parts.append(
        f'    <div class="cta-row"><a class="primary" href="/careers/?field={esc(cip)}">'
        "Explore this major &rarr;</a></div>\n"
    )

    # Degree ladder.
    parts.append('    <h2 class="sec">Median earnings by degree level</h2>\n')
    parts.append(
        '    <div class="tscroll"><table class="t"><thead><tr><th>Degree</th><th class="num">Median earnings</th>'
        '<th class="num">Typical range</th><th class="num">Schools</th>'
        '<th class="num">Clear the bar</th></tr></thead><tbody>\n'
    )
    for c in sorted(creds, key=lambda c: CRED_ORDER.get(c["credential"], 9)):
        rng = (
            f"{money(c['p25'])} to {money(c['p75'])}"
            if c.get("p25") is not None and c.get("p75") is not None
            else "n/a"
        )
        passp = "n/a" if c.get("pass_pct") is None else f"{c['pass_pct']}%"
        parts.append(
            f"      <tr><td>{esc(c['credential'])}</td><td class='num'>{money(c['med'])}</td>"
            f"<td class='num'>{rng}</td><td class='num'>{c.get('schools') or 'n/a'}</td>"
            f"<td class='num'>{passp}</td></tr>\n"
        )
    parts.append("    </tbody></table></div>\n")
    parts.append(
        '    <p class="src">"Clear the bar" is the share of programs whose graduates out-earn a '
        "typical high-school graduate (the federal earnings-premium test). Typical range is the "
        "25th to 75th percentile of program medians.</p>\n"
    )

    # BLS demand / outlook (from any credential row that carries it).
    demand = next((c["demand"] for c in creds if c.get("demand")), None)
    if demand:
        g = demand.get("growth_pct")
        opn = demand.get("annual_openings")
        gtxt = "n/a" if g is None else f"{g:+g}%"
        otxt = "n/a" if opn is None else f"{int(round(opn)):,}"
        parts.append('    <h2 class="sec">Job outlook</h2>\n')
        parts.append(
            f'    <p class="idline">Projected employment growth <b>{gtxt}</b> (2023 to 2033), about '
            f"<b>{otxt}</b> openings a year across the occupations this field commonly leads to.</p>\n"
        )
        occ = demand.get("occupations") or []
        if occ:
            parts.append(
                '    <div class="tscroll"><table class="t"><thead><tr><th>Occupation</th><th class="num">Median pay</th>'
                '<th class="num">Growth</th><th class="num">Openings/yr</th></tr></thead><tbody>\n'
            )
            for o in occ:
                w = money(o.get("wage"))
                gr = "n/a" if o.get("growth") is None else f"{o['growth']:+g}%"
                op = "n/a" if o.get("openings") is None else f"{int(round(o['openings'])):,}"
                parts.append(
                    f"      <tr><td>{esc(o.get('title'))}</td><td class='num'>{w}</td>"
                    f"<td class='num'>{gr}</td><td class='num'>{op}</td></tr>\n"
                )
            parts.append("    </tbody></table></div>\n")
            parts.append(
                '    <p class="src">Occupation pay and outlook: U.S. Bureau of Labor Statistics '
                "(OEWS wages, Employment Projections). A field maps to several occupations, so this "
                "lists where the major commonly leads, not any one graduate's job.</p>\n"
            )

    parts.append(
        '    <p class="src">Earnings source: U.S. Department of Education College Scorecard '
        "(release 2026-06-10), median earnings of graduates measured up to four years after "
        "completing. Figures describe past graduates and are never a promise. Method: "
        '<a href="/methodology/">methodology</a>. '
        '<a href="https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction">'
        "Report an error</a>.</p>\n"
    )
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append(BEACON)
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def majors_index(by_family) -> str:
    canonical = f"{BASE}/majors/"
    title = "What every college major pays"
    desc = (
        "Browse college majors to see median earnings by degree level, the range across schools, "
        "and the job outlook. Built on public federal data."
    )
    parts = [head(title, desc, canonical)]
    parts.append('  <main class="wrap pg">\n')
    parts.append('    <nav class="crumbs">Majors</nav>\n')
    parts.append("    <h1>What college majors pay</h1>\n")
    parts.append(
        '    <p class="idline">Median earnings by degree level and job outlook for each field of '
        'study, or <a href="/careers/">explore majors interactively</a>.</p>\n'
    )
    for family in sorted(by_family):
        parts.append(f'    <h2 class="sec">{esc(family)}</h2>\n')
        parts.append('    <ul class="schoollist">\n')
        for name, slug, lead in sorted(by_family[family], key=lambda x: x[0].lower()):
            parts.append(
                f'      <li><a href="/majors/{slug}/">{esc(name)}</a>'
                f'<div class="meta">graduates typically earn about {money(lead)}</div></li>\n'
            )
        parts.append("    </ul>\n")
    parts.append("  </main>\n")
    parts.append(FOOTER)
    parts.append(BEACON)
    parts.append("</body>\n</html>\n")
    return "".join(parts)


def main() -> None:
    con = duckdb.connect()
    fields = build_fields(con)

    # Group per 4-digit CIP (a "major"): each carries its credential ladder.
    majors: dict[str, dict] = {}
    for f in fields:
        m = majors.setdefault(
            f["cip"], {"cip": f["cip"], "name": f["name"], "family": f["family"], "creds": []}
        )
        m["creds"].append(f)

    # Stable unique slugs (name; on collision add the cip code).
    slugs, used = {}, set()
    for cip, m in sorted(majors.items(), key=lambda kv: kv[1]["name"].lower()):
        cand = slugify(m["name"])
        if cand in used:
            cand = f"{cand}-{cip}"
        used.add(cand)
        slugs[cip] = cand

    majors_dir = SITE / "majors"
    majors_dir.mkdir(parents=True, exist_ok=True)
    by_family: dict[str, list] = defaultdict(list)
    for cip, m in majors.items():
        slug = slugs[cip]
        d = majors_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(major_page(cip, m["name"], m["family"], m["creds"], slug))
        # Index by the plain name so the A-Z reads like a person wrote it, while the slug (and
        # therefore the URL) still derives from the official federal label.
        by_family[m["family"]].append(
            (plain_name(cip, m["name"]), slug, _headline(m["creds"])["med"])
        )

    (majors_dir / "index.html").write_text(majors_index(by_family))
    print(f"major pages: {len(majors):,}  |  families: {len(by_family)}")
    print(f"wrote -> {majors_dir}")


if __name__ == "__main__":
    main()
