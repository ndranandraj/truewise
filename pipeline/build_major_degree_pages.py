"""Generate a static page per major and degree: /majors/<major>/<degree>/ (Prototype L, approved
14 November 2026).

"Bachelor's in nursing" used to exist only as a row on /majors/<slug>/ and as a view the Careers
script draws at /careers/?field=5138&cred=3, which declares /careers/ as its canonical address and
so cannot be found on its own. This is the page for that unit, one per row of
build_careers.build_fields (720 in the June 2026 release).

Each page states, for one field at one degree level:
  * the median of the programs' medians, with how many programs it rests on, how many could not be
    assessed and why, and how many use 1-year earnings
  * the middle half of programs, and median debt with its own count
  * how many programs' graduates earned more than their state's high-school line, and how that
    relates to the federal earnings test, which uses that line for undergraduate programs only
  * the other degree levels in the field
  * the colleges where the most students complete it, with each program's own figures
  * the occupations the field commonly leads to (BLS), labelled as field-wide

The headline figures are build_fields' own, so a page shows the same numbers as /careers/ and
/majors/. The counts around them are recomputed here from the program table, and the build stops
if this module's median or count disagrees with build_fields: two pages of one site must not give
two medians for one thing.

No share card per page. The major's card carries the bachelor's figure, which would be wrong on a
master's page, and 720 more images would use a quarter of what is left of the 20,000 files a
deployment may hold. These pages use the site's default card.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_major_degree_pages
"""

from __future__ import annotations

import json
import statistics

import duckdb

from pipeline import build_careers as bc
from pipeline import profile_layout as pl
from pipeline.build_careers_demand import ep_years
from pipeline.build_college_pages import (
    BASE,
    BEACON,
    FOOTER,
    esc,
    head,
    known_state,
    money,
    state_label,
)
from pipeline.build_majors_pages import CRED_ORDER, major_slugs
from pipeline.build_package_data import SCORECARD_RELEASE
from pipeline.build_profile_pilot import GRAD_LEVELS
from pipeline.cip_names import has_plain_name, plain_name, short_label, tidy_official
from pipeline.config import ROOT
from pipeline.degree_levels import DEGREE, degree_path
from pipeline.program_unit import UNDERGRAD_LEVELS, programs_sql

SITE = ROOT / "site"
REPORT_URL = (
    "https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction"
    "&body=Page%20URL%3A%0AWhat%20looks%20wrong%3A%0AExpected%20value%20and%20source%3A"
)
TOP_COLLEGES = 20

# The federal rule does not pass or fail programs for tipped jobs in its first rounds, which changes
# what "fall short" means for them. Only the field the homepage already names is marked: the rule
# counts twenty six-digit program codes and they have not been transcribed here, so a page for
# another tipped field carries the general link to the explainer and no specific note.
TIPPED_CIP4 = {"1204": "cosmetology"}

PROGRAM_COLS = (
    "unitid",
    "inst_name",
    "state",
    "earnings",
    "earnings_horizon",
    "value_flag",
    "earnings_threshold_state",
    "debt_median",
    "completers_count",
)


def _n(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _growth(g: float) -> str:
    """Signed percent. A median can be -0.0, which would print as "-0%"."""
    return f"{g + 0.0:+g}%"


def all_programs(con) -> dict[tuple[str, str], list[dict]]:
    """Every program ED lists, grouped by (field, degree level). One row per college: campuses that
    share a federal aid number are one program (pipeline.program_unit).

    Read through build_careers' own warehouse path, so this module and build_fields cannot be
    pointed at different files."""
    vc = bc.PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    rows = con.execute(
        f"SELECT cip_code, credential_level, {', '.join(PROGRAM_COLS)} FROM {programs_sql(vc)} "
        "WHERE regexp_matches(unitid, '^[0-9]+$')"
    ).fetchall()
    out: dict[tuple[str, str], list[dict]] = {}
    for cip, cred, *rest in rows:
        out.setdefault((cip, cred), []).append(dict(zip(PROGRAM_COLS, rest, strict=True)))
    return out


def measure(rows: list[dict]) -> dict:
    """The counts and medians a page states. A figure that cannot be computed is None, and the page
    says why; nothing is defaulted to 0."""
    with_earn = [r for r in rows if r["earnings"] is not None]
    decided = [r for r in with_earn if r["value_flag"] != "insufficient_data"]
    debts = [r["debt_median"] for r in rows if r["debt_median"] is not None]
    return {
        "listed": len(rows),
        "decided": len(decided),
        "n_pass": sum(1 for r in decided if r["value_flag"] == "passes_earnings_premium"),
        "n_fail": sum(1 for r in decided if r["value_flag"] == "fails_earnings_premium"),
        "nobench": len(with_earn) - len(decided),
        "no_earn": len(rows) - len(with_earn),
        "one_year": sum(1 for r in decided if r["earnings_horizon"] == "1yr_after_completion"),
        "median": statistics.median(r["earnings"] for r in decided) if decided else None,
        "debt": statistics.median(debts) if debts else None,
        "n_debt": len(debts),
    }


def rest_text(m: dict) -> str:
    """What the programs without a comparison are, in the site's two terms for them."""
    rest = m["listed"] - m["decided"]
    if not rest:
        return ""
    verb = "has" if rest == 1 else "have"
    other = "The other one" if rest == 1 else f"The other {rest:,}"
    if m["nobench"] and m["no_earn"]:
        return (
            f"{other}: {m['nobench']:,} with earnings but no state benchmark and "
            f"{m['no_earn']:,} with no earnings published."
        )
    if m["nobench"]:
        return f"{other} {verb} earnings but no state benchmark."
    return f"{other} {verb} no earnings published."


def horizon_text(m: dict) -> str:
    """The earnings window stays beside the figure it qualifies."""
    if not m["one_year"]:
        return "All are measured four years after finishing."
    if m["one_year"] == m["decided"]:
        return "All use 1-year earnings, an earlier career stage."
    return (
        f"{m['one_year']:,} of the {m['decided']:,} use{'s' if m['one_year'] == 1 else ''} 1-year "
        "earnings, an earlier career stage; the rest are measured four years after finishing."
    )


def against_line(m: dict, cip: str, cred: str) -> str:
    """How many programs' graduates earned more than their state's high-school line, then whose
    comparison that is. The federal test uses this line for undergraduate programs only, so a
    graduate page says the comparison is not that test."""
    d, p, f = m["decided"], m["n_pass"], m["n_fail"]
    line = "a typical high-school graduate in the college&rsquo;s state"
    if f == 0:
        counts = f"In all {d:,} assessed programs, graduates earned more than {line}."
    elif p == 0:
        counts = f"In all {d:,} assessed programs, graduates earned less than {line}."
    else:
        counts = (
            f"In {p:,} of the {d:,} assessed programs, graduates earned more than {line}. "
            f"In {f:,}, they earned less."
        )
    link = '<a href="/earnings-test/">What the test is</a>'
    if cred in UNDERGRAD_LEVELS:
        rule = f'<p class="md-rule">{pl.RULE_UNDERGRADUATE} {link}</p>'
    elif cred in GRAD_LEVELS:
        rule = (
            f'<p class="md-rule">These are graduate programs. {pl.RULE_GRADUATE} So this '
            f"comparison is not that test. {link}</p>"
        )
    else:
        rule = (
            '<p class="md-rule">This comparison is Truewise&rsquo;s calculation on published '
            'earnings. <a href="/earnings-test/">How it relates to the federal earnings test</a></p>'
        )
    tipped = ""
    if cip in TIPPED_CIP4 and cred in UNDERGRAD_LEVELS:
        tipped = (
            '\n      <p class="caveat">The federal rule holds programs for tipped jobs, '
            f"{TIPPED_CIP4[cip]} among them, out of its first rounds: ED does not pass or fail them "
            'while it evaluates tax year 2025 or earlier. <a href="/earnings-test/#held">Held out '
            "at first</a></p>"
        )
    return f"      <p>{counts}</p>\n      {rule}{tipped}"


def ladder(f: dict, siblings: list[dict], slug: str) -> str:
    """The field at each degree level. Every sibling has its own page, because the pages are built
    from the same rows this table lists."""
    rows = []
    for c in sorted(siblings, key=lambda c: (CRED_ORDER.get(c["credential"], 9), c["cred"])):
        here = c["cred"] == f["cred"]
        href = degree_path(slug, c["cred"])
        label = DEGREE[c["cred"]].heading
        if here:
            name = (
                f'<a href="{href}" aria-current="page">{label}</a> '
                '<span class="md-tag">This page</span>'
            )
        else:
            name = f'<a href="{href}">{label}</a>'
        band = (
            f"{money(c['p25'])} to {money(c['p75'])}"
            if c["p25"] is not None and c["p75"] is not None
            else "not assessed"
        )
        cur = ' class="md-cur"' if here else ""
        rows.append(
            f"        <tr{cur}><td>{name}</td>"
            f'<td class="num">{money(c["med"])}</td><td class="num">{band}</td>'
            f'<td class="num">{c["programs"]:,}</td></tr>'
        )
    return (
        '      <div class="tscroll" tabindex="0" role="region" aria-label="Earnings by degree level">'
        '<table class="t"><thead><tr><th>Degree</th><th class="num">Median earnings</th>'
        '<th class="num">Middle half of programs</th><th class="num">Programs assessed</th>'
        "</tr></thead><tbody>\n" + "\n".join(rows) + "\n      </tbody></table></div>"
    )


def colleges(rows: list[dict], profiles: dict[str, str], plain: str, adjective: str) -> str:
    """The colleges where the most students complete it, with each program's own figures.

    Ordered by completions, the major page's rule: it says where people study, and is not a
    judgement about where to. Ties go to the lower UNITID, so a tie cannot move a row between
    builds. A college is linked only where it has a profile."""
    counted = [r for r in rows if (r["completers_count"] or 0) > 0]
    picks = sorted(counted, key=lambda r: (-r["completers_count"], r["unitid"]))[:TOP_COLLEGES]
    if not picks:
        return ""
    body = []
    for r in picks:
        name = esc(r["inst_name"])
        slug = profiles.get(r["unitid"])
        if slug:
            name = f'<a href="/college/{esc(slug)}/">{name}</a>'
        st = state_label(r["state"]) if known_state(r["state"]) else "state not reported"
        if r["earnings"] is None:
            earn, gap_txt = "not published", "not assessed"
        else:
            early = (
                ' <span class="md-oneyr">1-year earnings</span>'
                if r["earnings_horizon"] == "1yr_after_completion"
                else ""
            )
            earn = f"{money(r['earnings'])}{early}"
            if r["earnings_threshold_state"] is None:
                gap_txt = "no state benchmark"
            else:
                gap = r["earnings"] - r["earnings_threshold_state"]
                gap_txt = f"{'+' if gap >= 0 else '-'}{money(abs(gap))}"
        body.append(
            f'        <tr><td>{name}<span class="md-st">{esc(st)}</span></td>'
            # One wrapper, so the stacked phone layout keeps the figure and its marker together.
            f'<td class="num"><span class="md-cell">{earn}</span></td>'
            f'<td class="num">{gap_txt}</td>'
            f'<td class="num">{int(r["completers_count"]):,}</td></tr>'
        )
    shown = (
        f"The {len(picks)} colleges where the most students complete"
        if len(picks) > 1
        else "The one college that reports students completing"
    )
    return f"""    <section id="colleges" aria-labelledby="colleges-h">
      <h2 id="colleges-h">Where the most students complete it</h2>
      <p>{shown} a {adjective} program in {esc(plain)},
        of {len(counted):,} that report completions. Ordered by number of completions only: this is
        where people study it, not a judgement about where to.</p>
      <div class="tscroll" tabindex="0" role="region" aria-label="Largest programs"><table class="t"><thead><tr><th>College</th><th class="num">Median earnings</th><th class="num">vs a high-school grad</th><th class="num">Recent completers</th></tr></thead><tbody>
{chr(10).join(body)}
      </tbody></table></div>
      <p class="chart-src">Each row is that college&rsquo;s own program. A college whose campuses
        share one federal aid number is counted once, with its campuses&rsquo; completions added.</p>
    </section>
"""


def outlook(f: dict) -> str:
    """BLS occupations for the field. The mapping is by field, not by degree level, and says so."""
    d = f.get("demand")
    if not d or not d.get("occupations"):
        return ""
    g, opn = d.get("growth_pct"), d.get("annual_openings")
    gtxt = "not published" if g is None else _growth(g)
    otxt = "not published" if opn is None else f"{int(round(opn)):,}"
    start, end = ep_years(d["vintage"]["ep"])
    rows = []
    for o in d["occupations"]:
        gr = "not published" if o.get("growth") is None else _growth(o["growth"])
        op = "not published" if o.get("openings") is None else f"{int(round(o['openings'])):,}"
        rows.append(
            f"        <tr><td>{esc(o.get('title'))}</td><td class='num'>{money(o.get('wage'))}</td>"
            f"<td class='num'>{gr}</td><td class='num'>{op}</td></tr>"
        )
    return f"""    <section id="jobs" aria-labelledby="jobs-h">
      <h2 id="jobs-h">Jobs this field commonly leads to</h2>
      <p>Projected employment growth of <b>{gtxt}</b> from {start} to {end}, and about <b>{otxt}</b>
        openings a year, across these occupations. They are matched to the field at every degree
        level, not to this degree, and the same occupations serve other majors.</p>
      <div class="tscroll" tabindex="0" role="region" aria-label="Related occupations"><table class="t"><thead><tr><th>Occupation</th><th class="num">Median pay</th><th class="num">Growth</th><th class="num">Openings a year</th></tr></thead><tbody>
{chr(10).join(rows)}
      </tbody></table></div>
    </section>
"""


def title_and_desc(f: dict) -> tuple[str, str]:
    """Query first, one figure, and "median" always beside it. A search result cuts a title near 60
    characters and a description at 155, so a long field name takes the shorter form of each. A
    title can still run long when the field's own name does; the degree and field come first, so a
    cut title still names the page."""
    level = DEGREE[f["cred"]]
    med = money(f["med"])
    short = short_label(f["cip"], f["name"])
    title = f"{level.title} in {short}: what graduates earn ({med} median)"
    if len(title) > 60:
        title = f"{level.title} in {short}: {med} median earnings"
    adjective = level.adjective.replace("&rsquo;", "'")
    plain = plain_name(f["cip"], f["name"])
    n = _n(f["programs"], "program")
    desc = (
        f"Graduates of the median {adjective} program in {plain} earned {med} a year. Based on "
        f"{n}, with the range, debt and the largest colleges."
    )
    if len(desc) > 155:
        desc = f"Graduates of the median {adjective} program in {plain} earned {med} a year ({n})."
    if len(desc) > 155:
        desc = (
            f"{level.title} in {short}: the median program's graduates earned {med} a year ({n})."
        )
    return title, desc


def degree_page(
    f: dict, siblings: list[dict], rows: list[dict], slug: str, profiles: dict[str, str]
) -> str:
    m = measure(rows)
    if m["median"] is None or int(round(m["median"])) != f["med"] or m["decided"] != f["programs"]:
        raise SystemExit(
            f"{f['cip']} x {f['cred']}: this page's median and count ({m['median']}, "
            f"{m['decided']}) differ from build_fields ({f['med']}, {f['programs']}). Two pages "
            "would give two figures for one thing."
        )
    level = DEGREE[f["cred"]]
    plain = plain_name(f["cip"], f["name"])
    official = tidy_official(f["name"])
    title, desc = title_and_desc(f)
    canonical = f"{BASE}{degree_path(slug, f['cred'])}"
    crumb = level.heading.replace("&rsquo;", "'")
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Majors","item":"{BASE}/majors/"}},
    {{"@type":"ListItem","position":2,"name":{json.dumps(plain)},"item":"{BASE}/majors/{slug}/"}},
    {{"@type":"ListItem","position":3,"name":{json.dumps(crumb)},"item":"{canonical}"}}
  ]}}
  </script>
"""
    page_head = head(title, desc, canonical, ld).replace(
        "</head>", '  <link rel="stylesheet" href="/article.css" />\n</head>', 1
    )
    idline = esc(f["family"])
    if has_plain_name(f["cip"]) and official.lower() != plain.lower():
        idline += f" &middot; federal classification: {esc(official)}"
    band = (
        f"<b>{money(f['p25'])} to {money(f['p75'])}</b><span>A quarter of the {m['decided']:,} "
        "programs are below this range and a quarter above it.</span>"
        if f["p25"] is not None and f["p75"] is not None
        else "<b>not assessed</b>"
    )
    debt = (
        f"<b>{money(m['debt'])}</b><span>Federal loans only. The middle of the "
        f"{_n(m['n_debt'], 'program')} that report{'s' if m['n_debt'] == 1 else ''} it.</span>"
        if m["debt"] is not None
        else "<b>not reported</b><span>No program in this group reports a debt figure.</span>"
    )
    adj = level.adjective
    body = f"""  <main class="wrap art md">
    <nav class="crumbs"><a href="/majors/">Majors</a> &rsaquo; <a href="/majors/{slug}/">{esc(plain)}</a> &rsaquo; {level.heading}</nav>
    <h1>{level.heading} in {esc(plain)}: what graduates earn</h1>
    <p class="idline">{idline}</p>

    <div class="kf" role="group" aria-labelledby="kf-label">
      <p class="kf__label" id="kf-label">Median graduate earnings</p>
      <div class="kf__figure"><span class="kf__num">{money(f["med"])}</span><span class="kf__of">a year, the middle of {_n(m["decided"], adj + " program")}</span></div>
      <p class="kf__text">Each program reports the median earnings of its own graduates. Half of the
        {m["decided"]:,} programs are above this figure and half below.</p>
      <p class="kf__qual"><b>{m["decided"]:,} of the {m["listed"]:,} {adj} programs ED lists in this
        field could be assessed.</b> {rest_text(m)} {horizon_text(m)}</p>
    </div>

    <ul class="md-facts">
      <li><span class="md-facts__k">Middle half of programs</span><span class="md-facts__v">{band}</span></li>
      <li><span class="md-facts__k">Median debt at graduation</span><span class="md-facts__v">{debt}</span></li>
    </ul>

    <section id="line" aria-labelledby="line-h">
      <h2 id="line-h">Compared with a high-school graduate</h2>
{against_line(m, f["cip"], f["cred"])}
    </section>

    <section id="degrees" aria-labelledby="degrees-h">
      <h2 id="degrees-h">{esc(plain)} at each degree level</h2>
{ladder(f, siblings, slug)}
    </section>

{colleges(rows, profiles, plain, adj)}
{outlook(f)}
    <section id="sources" aria-labelledby="sources-h">
      <h2 id="sources-h">Sources and definitions</h2>
      <ul class="srcs">
        <li>U.S. Department of Education, College Scorecard, release {SCORECARD_RELEASE}. Earnings
          are medians for graduates who received federal aid. Debt is federal loans only.</li>
        <li><b>A program</b> is one college&rsquo;s offering of this field at this degree level,
          counted once per college.</li>
        <li><b>Assessed</b> means ED publishes the program&rsquo;s earnings and a high-school
          benchmark for the college&rsquo;s state. <b>No earnings published</b> usually means too
          few graduates were measured. Neither is a judgement of a program.</li>
        <li>Occupations: U.S. Bureau of Labor Statistics, wages and employment projections.</li>
      </ul>
      <p class="md-next"><a class="btn" href="/value-check/">Look up a college</a>
        <a class="btn btn--secondary" href="/majors/{slug}/">All of {esc(plain)}</a>
        <a class="btn btn--text" href="/methodology/">How we count</a>
        <a class="btn btn--text" href="{REPORT_URL}">Report an error</a></p>
    </section>
  </main>
"""
    return page_head + body + FOOTER + BEACON + "</body>\n</html>\n"


def profile_slugs(con) -> dict[str, str]:
    """{UNITID: slug} for every college that gets a profile, from the same model and registry the
    profile builder uses, so a link here cannot point at a page that is not built."""
    from pipeline import build_site as _bs
    from pipeline.build_college_pages import build_slugs, qualifying_schools

    if not (_bs.PARQUET_DIR / "value_check.parquet").exists():
        return {}
    all_schools, _, _ = _bs.build_model(con)
    return build_slugs(qualifying_schools(all_schools))


def main() -> None:
    con = duckdb.connect()
    fields = bc.build_fields(con)
    unknown = sorted({f["cred"] for f in fields} - set(DEGREE))
    if unknown:
        raise SystemExit(
            f"degree levels with no entry in pipeline.degree_levels: {unknown}. A page needs a "
            "name and an address, and neither is guessed."
        )
    by_cip: dict[str, list[dict]] = {}
    for f in fields:
        by_cip.setdefault(f["cip"], []).append(f)
    slugs = major_slugs(fields)
    programs = all_programs(con)
    profiles = profile_slugs(con)

    majors_dir = SITE / "majors"
    for f in fields:
        html = degree_page(
            f, by_cip[f["cip"]], programs.get((f["cip"], f["cred"]), []), slugs[f["cip"]], profiles
        )
        d = majors_dir / slugs[f["cip"]] / DEGREE[f["cred"]].slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")
    print(f"major and degree pages: {len(fields):,}")
    print(f"wrote -> {majors_dir}/<major>/<degree>/")


if __name__ == "__main__":
    main()
