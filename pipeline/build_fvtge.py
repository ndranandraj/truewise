"""Finding: which colleges had not filed their FVT/GE data, and what the Scorecard shows about them.

Built from two committed sources:
  * published/fvtge_reporting.parquet: ED's list of which of the seven required FVT/GE file
    components each institution had submitted, as compiled on 6 August 2026 (see
    pipeline/build_fvtge_source.py for provenance).
  * published/value_check.parquet: our program-level College Scorecard earnings test.

Two things are published, and they are kept separate on purpose:
  1. ED's reporting status, restated. Counts by sector, component and state, plus every institution
     on ED's list, searchable and downloadable. "Submitted" is ED's word for "a file arrived"; ED has
     not judged completeness. Nothing here says an institution's data is complete or incomplete.
  2. An association in OUR data. Programs at institutions ED lists with components not submitted
     fail the Scorecard earnings-premium test more often. Part of that is composition (more
     for-profit, more certificates), so the page leads with a comparison standardised to sector and
     credential. It is an association, it uses Scorecard earnings rather than any FVT/GE filing, and
     it is not evidence that a missing file hides anything.

Writes site/findings/fvtge-reporting/ (page, institutions.json for the search, CSV).

Usage:
    python -m pipeline.build_fvtge
"""

from __future__ import annotations

import csv
import json

import duckdb

from pipeline.build_college_pages import BASE, BEACON, FOOTER, STATE_NAMES, esc, head, state_label
from pipeline.config import ROOT
from pipeline.og_images import card as render_card
from pipeline.program_unit import programs_sql
from pipeline.tokens_gen import BAD as OG_BAD

SITE = ROOT / "site"
PUBLISHED = ROOT / "published"
SLUG = "fvtge-reporting"
OUT_DIR = SITE / "findings" / SLUG
# The dateline. UPDATED_ON is an editorial date: advance it when the finding's wording, figures or
# presentation change, never automatically on a cosmetic or unrelated deploy. The data's own date
# ("as of 6 August 2026") comes from ED's compile date and is separate.
PUBLISHED_ON = "23 Sep 2026"
UPDATED_ON = "2 Oct 2026"

COMPONENT_LABELS = [
    ("total2223", "Student file, total amounts, 2022-23"),
    ("program2324", "Program file, 2023-24"),
    ("annual2324", "Student file, annual amounts, 2023-24"),
    ("total2324", "Student file, total amounts, 2023-24"),
    ("program2425", "Program file, 2024-25"),
    ("annual2425", "Student file, annual amounts, 2024-25"),
    ("total2425", "Student file, total amounts, 2024-25"),
]
SECTOR_ORDER = ["Public", "Private Non-Profit", "Private For-Profit", "Foreign"]
SECTOR_LABEL = {
    "Public": "Public",
    "Private Non-Profit": "Private nonprofit",
    "Private For-Profit": "Private for-profit",
    "Foreign": "Foreign institutions",
}
CRED_ORDER = ["Undergraduate Certificate or Diploma", "Associate's Degree", "Bachelor's Degree"]
CRED_LABEL = {
    "Undergraduate Certificate or Diploma": "Undergraduate certificate",
    "Associate's Degree": "Associate's degree",
    "Bachelor's Degree": "Bachelor's degree",
}
# ED's words, quoted exactly from the spreadsheet's Overview and Frequencies sheets.
ED_COMPLETENESS = (
    "The data do not confirm that a submission is complete; rather, it only indicates that the "
    "college submitted a file (regardless of the file’s completeness)."
)
ED_NOT_SUBMITTED = (
    "“Not Submitted” means no file was submitted at all, even though the institution was "
    "required to under the Department’s regulations."
)


def _con(ed_path=None, vc_path=None):
    con = duckdb.connect()
    ed = ed_path or PUBLISHED / "fvtge_reporting.parquet"
    vc = vc_path or PUBLISHED / "value_check.parquet"
    con.execute(f"CREATE VIEW ed AS SELECT * FROM read_parquet('{ed}')")
    con.execute(
        # Each program counted once (pipeline/program_unit.py); the join to ED's list is by OPEID6.
        f"CREATE VIEW vc AS SELECT * FROM {programs_sql(vc)} WHERE regexp_matches(unitid, '^[0-9]+$')"
    )
    return con


def compute(con) -> dict:
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
    # "Submitted no file" counts colleges with no component marked Submitted: every required one
    # was Not Submitted and the rest Not Required. "All seven" (num_miss = 7) is a subset of it.
    none_filed_sql = "count(*) FILTER (WHERE num_miss > 0 AND NOT (total2223 = 'Submitted' OR program2324 = 'Submitted' OR annual2324 = 'Submitted' OR total2324 = 'Submitted' OR program2425 = 'Submitted' OR annual2425 = 'Submitted' OR total2425 = 'Submitted'))"
    total, missing, all7, none_filed = q(
        "SELECT count(*), count(*) FILTER (WHERE num_miss > 0), count(*) FILTER (WHERE num_miss = 7), "
        f"{none_filed_sql} FROM ed"
    )[0]
    compiled = q("SELECT any_value(compiled) FROM ed")[0][0]

    sectors = []
    for control, n, m, a, nf in q(
        "SELECT control, count(*), count(*) FILTER (WHERE num_miss > 0), "
        f"count(*) FILTER (WHERE num_miss = 7), {none_filed_sql} FROM ed GROUP BY 1"
    ):
        sectors.append({"sector": control, "n": n, "missing": m, "all7": a, "none_filed": nf})
    sectors.sort(
        key=lambda s: SECTOR_ORDER.index(s["sector"]) if s["sector"] in SECTOR_ORDER else 99
    )

    components = []
    for key, label in COMPONENT_LABELS:
        ns, nr = q(
            f"SELECT count(*) FILTER (WHERE {key} = 'Not Submitted'), "
            f"count(*) FILTER (WHERE {key} = 'Not Required') FROM ed"
        )[0]
        components.append({"key": key, "label": label, "not_submitted": ns, "not_required": nr})

    states = [
        {"state": s, "n": n, "missing": m, "all7": a, "none_filed": nf}
        for s, n, m, a, nf in q(
            "SELECT stabbr, count(*), count(*) FILTER (WHERE num_miss > 0), "
            f"count(*) FILTER (WHERE num_miss = 7), {none_filed_sql} FROM ed GROUP BY 1 ORDER BY 3 DESC, 1"
        )
    ]

    matched = q("SELECT count(DISTINCT e.opeid6) FROM ed e JOIN vc v USING (opeid6)")[0][0]

    # The association. Programs with an earnings verdict, at institutions on ED's list.
    con.execute(
        """CREATE OR REPLACE TEMP VIEW judged AS
        SELECT v.control AS sector, v.credential_desc AS cred, e.num_miss > 0 AS missing,
               v.value_flag = 'fails_earnings_premium' AS fail
        FROM vc v JOIN ed e USING (opeid6)
        WHERE v.value_flag IN ('passes_earnings_premium', 'fails_earnings_premium')"""
    )
    raw = {
        m: (n, f)
        for m, n, f in q("SELECT missing, count(*), sum(fail::INT) FROM judged GROUP BY 1")
    }
    # Standardise: apply complete filers' fail rate in each sector x credential cell to the missing
    # filers' own mix. Cells with no complete-filer programs cannot be standardised and are reported.
    std = q(
        """WITH cell AS (
             SELECT sector, cred,
                    count(*) FILTER (WHERE missing) AS nm,
                    avg(fail::INT) FILTER (WHERE NOT missing) AS rc
             FROM judged GROUP BY 1, 2)
           SELECT sum(nm * rc) / sum(nm) FILTER (WHERE rc IS NOT NULL),
                  sum(nm) FILTER (WHERE rc IS NULL)
           FROM cell"""
    )[0]
    cells = []
    for sector, cred, nm, fm, nc, fc in q(
        """SELECT sector, cred,
                  count(*) FILTER (WHERE missing), sum(fail::INT) FILTER (WHERE missing),
                  count(*) FILTER (WHERE NOT missing), sum(fail::INT) FILTER (WHERE NOT missing)
           FROM judged GROUP BY 1, 2"""
    ):
        if cred in CRED_ORDER and nm and nc:
            cells.append(
                {
                    "sector": sector,
                    "cred": cred,
                    "n_missing": nm,
                    "fail_missing": fm or 0,
                    "n_complete": nc,
                    "fail_complete": fc or 0,
                }
            )
    order = {"Public": 0, "Private, nonprofit": 1, "Private, for-profit": 2}
    cells.sort(key=lambda c: (order.get(c["sector"], 9), CRED_ORDER.index(c["cred"])))

    nm, fm = raw.get(True, (0, 0))
    nc, fc = raw.get(False, (0, 0))
    return {
        "compiled": compiled,
        "total": total,
        "missing": missing,
        "all7": all7,
        "none_filed": none_filed,
        "sectors": sectors,
        "components": components,
        "states": states,
        "matched": matched,
        "assoc": {
            "n_missing": nm,
            "fail_missing": fm,
            "n_complete": nc,
            "fail_complete": fc,
            "expected_missing": std[0],
            "unstandardised": std[1] or 0,
        },
        "cells": cells,
    }


def institutions(con) -> list[dict]:
    """One row per institution on ED's list, with what Truewise publishes about it."""
    registry = json.loads((PUBLISHED / "slug_registry.json").read_text())
    rows = con.execute(
        """SELECT e.opeid6, e.instnm, e.stabbr, e.control, e.num_miss,
                  e.total2223, e.program2324, e.annual2324, e.total2324,
                  e.program2425, e.annual2425, e.total2425,
                  list(DISTINCT v.unitid ORDER BY v.unitid) FILTER (WHERE v.unitid IS NOT NULL) AS unitids,
                  count(v.unitid) AS programs,
                  count(v.unitid) FILTER (WHERE v.value_flag != 'insufficient_data') AS judged,
                  count(v.unitid) FILTER (WHERE v.value_flag = 'fails_earnings_premium') AS fail
           FROM ed e LEFT JOIN vc v USING (opeid6)
           GROUP BY ALL ORDER BY e.stabbr, e.instnm"""
    ).fetchall()
    out = []
    for r in rows:
        unitids = r[12] or []
        slugs = [registry[u] for u in unitids if u in registry]
        out.append(
            {
                "opeid6": r[0],
                "name": r[1],
                "state": r[2],
                "sector": r[3],
                "not_submitted": r[4],
                "components": dict(zip([k for k, _ in COMPONENT_LABELS], r[5:12], strict=True)),
                "programs": r[13],
                "judged": r[14],
                "fail": r[15],
                "profile": f"/college/{slugs[0]}/" if len(slugs) == 1 else None,
                "campuses": len(unitids),
            }
        )
    return out


def _pct(a, b) -> int:
    return round(100 * a / b) if b else 0


def _date(iso: str) -> str:
    y, m, d = iso.split("-")
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return f"{int(d)} {months[int(m) - 1]} {y}"


def _pct1(a, b) -> str:
    return f"{100 * a / b:.1f}" if b else "0.0"


def _place_row(x) -> str:
    label = "Foreign institutions" if x["state"] == "FC" else state_label(x["state"])
    return (
        f"<tr><td>{esc(label)}</td><td class='num'>{x['n']:,}</td>"
        f"<td class='num'>{x['missing']:,} ({_pct(x['missing'], x['n'])}%)</td></tr>"
    )


NAV_ITEMS = [
    ("why", "Why it matters"),
    ("sector", "By sector"),
    ("files", "Which files"),
    ("places", "By state"),
    ("earnings", "Earnings link"),
    ("lookup", "Look up a college"),
    ("method", "Method"),
]


def render_page(s) -> str:
    """The finding in the article template approved as Prototype A (design plan, 27 September 2026).

    Styles come from /article.css, loaded by finding pages only, so no other page changes."""
    canonical = f"{BASE}/findings/{SLUG}/"
    when = _date(s["compiled"])
    short_when = when.rsplit(" ", 1)[0]
    total, missing = s["total"], s["missing"]
    a = s["assoc"]
    r_miss = 100 * a["fail_missing"] / a["n_missing"]
    r_comp = 100 * a["fail_complete"] / a["n_complete"]
    r_exp = 100 * a["expected_missing"]
    title = "Which colleges had not filed their federal earnings-transparency data?"
    desc = (
        f"As of {when}, the Department of Education listed {missing:,} of {total:,} colleges as "
        f"not having submitted at least one required FVT/GE file; {s['none_filed']:,} had submitted no file at all. "
        "Searchable by college, with what the Scorecard shows about them."
    )
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Findings","item":"{BASE}/findings/"}},
    {{"@type":"ListItem","position":2,"name":"FVT/GE reporting status","item":"{canonical}"}}
  ]}}
  </script>
"""
    render_card(
        SITE / "og" / "findings" / f"{SLUG}.png",
        f"Finding · federal reporting status, as of {when}",
        "Colleges that had not filed their FVT/GE data",
        big=f"{missing:,} of {total:,}",
        big_color=OG_BAD,
        sub=f"{s['none_filed']:,} had submitted no file at all.",
    )
    page_head = head(title, desc, canonical, ld, og_image=f"/og/findings/{SLUG}.png").replace(
        "</head>", '  <link rel="stylesheet" href="/article.css" />\n</head>', 1
    )

    # Sectors. Foreign institutions are a location group in ED's list, not a sector, so they are
    # stated beside the chart rather than drawn as a fourth bar (review, 27 September).
    real = [x for x in s["sectors"] if x["sector"] != "Foreign"]
    foreign_sector = next((x for x in s["sectors"] if x["sector"] == "Foreign"), None)
    bars = "".join(
        f'<li><span class="bars__name">{esc(SECTOR_LABEL.get(x["sector"], x["sector"]))}</span>'
        f'<span class="bars__track" aria-hidden="true"><span class="bars__fill" '
        f'style="width:{_pct1(x["missing"], x["n"])}%"></span></span>'
        f'<span class="bars__val"><b>{_pct(x["missing"], x["n"])}%</b>{x["missing"]:,} of '
        f"{x['n']:,} colleges</span></li>"
        for x in real
    )
    foreign_note = (
        f"<p>ED lists foreign institutions separately from the three sectors: "
        f"{foreign_sector['missing']:,} of {foreign_sector['n']:,} "
        f"({_pct(foreign_sector['missing'], foreign_sector['n'])}%) had at least one file not "
        "submitted.</p>"
        if foreign_sector
        else ""
    )
    comps = "".join(
        f"<tr><td>{esc(c['label'])}</td><td class='num'>{c['not_submitted']:,}</td>"
        f"<td class='num'>{c['not_required']:,}</td></tr>"
        for c in s["components"]
    )

    # Locations. Every code must have a name; ED's list includes territories and the freely
    # associated states (Marshall Islands, Micronesia, Palau) as well as the 50 states and DC.
    unnamed = [
        x["state"] for x in s["states"] if x["state"] not in STATE_NAMES and x["state"] != "FC"
    ]
    if unnamed:
        raise ValueError(f"location codes with no name: {unnamed}")
    places = [x for x in s["states"] if x["state"] in STATE_NAMES]
    foreign = next((x for x in s["states"] if x["state"] == "FC"), None)
    top = sorted(
        [x for x in places if x["n"] >= 30], key=lambda x: (-x["missing"] / x["n"], x["state"])
    )[:8]
    every = sorted(places, key=lambda x: state_label(x["state"])) + ([foreign] if foreign else [])
    top_rows = "".join(_place_row(x) for x in top)
    all_rows = "".join(_place_row(x) for x in every)
    foreign_line = (
        f"<p>Foreign institutions are listed separately by ED: {foreign['missing']:,} of "
        f"{foreign['n']:,} ({_pct(foreign['missing'], foreign['n'])}%) had at least one file not "
        "submitted.</p>"
        if foreign
        else ""
    )
    cells = "".join(
        f"<tr><td>{esc(c['sector'])}, {esc(CRED_LABEL[c['cred']].lower())}</td>"
        f"<td class='num'>{_pct1(c['fail_missing'], c['n_missing'])}% of {c['n_missing']:,}</td>"
        f"<td class='num'>{_pct1(c['fail_complete'], c['n_complete'])}% of {c['n_complete']:,}</td></tr>"
        for c in s["cells"]
    )
    chips = "".join(f'<li><a href="#{i}">{t}</a></li>' for i, t in NAV_ITEMS)
    csv_name = f"fvtge-reporting-{s['compiled']}.csv"
    thead = (
        '<thead><tr><th>{}</th><th class="num">Colleges listed</th>'
        '<th class="num">At least one not submitted</th></tr></thead>'
    )

    body = f"""  <main class="wrap art has-rail">
    <aside class="rail" aria-label="On this page"><div class="rail__inner"><h2>On this page</h2><ul>{chips}</ul></div></aside>
    <nav class="crumbs"><a href="/findings/">Findings</a> &rsaquo; FVT/GE reporting status</nav>
    <h1>{esc(title)}</h1>
    <p class="dateline"><span>Published {PUBLISHED_ON}</span><span>updated {UPDATED_ON}</span></p>

    <div class="kf" role="group" aria-labelledby="kf-label">
      <p class="kf__label" id="kf-label">Key finding</p>
      <div class="kf__figure"><span class="kf__num">{missing:,}</span><span class="kf__of">of {total:,} colleges</span></div>
      <p class="kf__text">({_pct(missing, total)}%) had not submitted at least one of the seven required FVT/GE files for the
        2024 and 2025 reporting cycles, as recorded in ED&rsquo;s list compiled on {when}.</p>
      <p class="kf__qual"><b>&ldquo;Submitted&rdquo; does not mean &ldquo;complete&rdquo;.</b> Files
        rejected with errors count as not submitted. Filings after {short_when} are not reflected.</p>
      <p class="kf__more"><span><b>{s["none_filed"]:,}</b> submitted no file at all</span>
        <span><b>{s["all7"]:,}</b> of those had all seven marked not submitted</span></p>
    </div>

    <nav class="sectnav" aria-label="Sections">
      <p class="sectnav__label" id="sn-l">{len(NAV_ITEMS)} sections</p>
      <div class="sectnav__scroll"><ul aria-labelledby="sn-l">{chips}</ul></div>
    </nav>

    <section id="why" class="why" aria-labelledby="why-h">
      <h2 id="why-h">Why it matters</h2>
      <p>These files are what the Department intends to use for the program-level data and statistics
        it plans to publish in 2027. Colleges have until 15 January 2027 to submit anything missing
        from the 2024 and 2025 cycles, and the 2026 cycle was due 1 October 2026, after ED compiled this list.</p>
      <p>The list records whether a file arrived, not why one did not. It is a status report, not a
        finding about any college&rsquo;s programs.</p>
    </section>

    <section id="sector" aria-labelledby="sector-h">
      <h2 id="sector-h">By sector</h2>
      <p class="chart-title">Colleges with at least one required file not submitted, by sector, as
        recorded by ED on {when}</p>
      <ul class="bars" aria-label="Share of listed colleges with at least one required file not submitted, by sector">{bars}</ul>
      <p class="chart-src">Bar length is the share of that sector&rsquo;s listed colleges. Source: ED,
        FVTGEDataReportingFinal.xlsx.</p>
      {foreign_note}
    </section>

    <section id="files" aria-labelledby="files-h">
      <h2 id="files-h">Which files were missing</h2>
      <p>Counts of colleges for each required component. &ldquo;Not required&rdquo; is ED&rsquo;s own
        status, for example a college that was not operating that year.</p>
      <div class="tscroll" tabindex="0" role="region" aria-label="Reporting status by file"><table class="t"><thead><tr><th>Required component</th><th class="num">Not submitted</th><th class="num">Not required</th></tr></thead><tbody>{comps}</tbody></table></div>
    </section>

    <section id="places" aria-labelledby="places-h">
      <h2 id="places-h">By state and territory</h2>
      <p>The eight states and territories with the highest share, among those with at least 30 listed colleges.</p>
      <div class="tscroll" tabindex="0" role="region" aria-label="Highest shares by state or territory"><table class="t">{thead.format("State or territory")}<tbody>{top_rows}</tbody></table></div>
      {foreign_line}
      <details class="more"><summary>All {len(every)} locations in ED&rsquo;s list</summary>
        <div class="tscroll" tabindex="0" role="region" aria-label="Every location in ED&rsquo;s list"><table class="t">{thead.format("Location")}<tbody>{all_rows}</tbody></table></div>
      </details>
    </section>

    <section id="earnings" aria-labelledby="earnings-h">
      <h2 id="earnings-h">What the College Scorecard shows about these colleges</h2>
      <p>Using the Scorecard earnings Truewise already publishes, not the FVT/GE files: the share of
        programs whose graduates earn less than a typical high-school graduate in their state.</p>
      <div class="stats">
        <div class="stat"><p class="stat__kind">Observed</p><div class="stat__fig">{r_comp:.1f}%</div><p class="stat__lab">all required files submitted</p></div>
        <div class="stat stat--est"><p class="stat__kind">Expected</p><div class="stat__fig">{r_exp:.1f}%</div><p class="stat__lab">for the other colleges, after allowing for sector and credential</p></div>
        <div class="stat stat--em"><p class="stat__kind">Observed</p><div class="stat__fig">{r_miss:.1f}%</div><p class="stat__lab">at least one file not submitted</p></div>
      </div>
      <p class="caveat">This is an association, not an explanation. About {r_miss - r_exp:.1f} points of
        the gap remain after allowing for sector and credential, and nothing here shows that a missing
        file hides worse results.</p>
      <details class="more"><summary>The nine sector and credential groups</summary>
        <div class="tscroll" tabindex="0" role="region" aria-label="Fail rate by sector and credential"><table class="t"><thead><tr><th>Group</th><th class="num">A file not submitted</th><th class="num">All submitted</th></tr></thead><tbody>{cells}</tbody></table></div>
      </details>
    </section>

    <section id="lookup" aria-labelledby="lookup-h">
      <h2 id="lookup-h">Look up a college</h2>
      <div class="lookup">
        <label for="lk-q">College name</label>
        <div class="searchbox"><input id="lk-q" type="search" autocomplete="off" placeholder="e.g. Palomar" aria-describedby="lk-status" /></div>
        <p class="lookup__status" id="lk-status" role="status" aria-live="polite">Type two or more letters of a college&rsquo;s name.</p>
        <ul class="lookup__rows" id="lk-rows"></ul>
        <noscript><p>Searching needs JavaScript. Every college on the list is in the CSV below.</p></noscript>
        <a class="btn btn--secondary" href="/findings/{SLUG}/{csv_name}" download>Download all {total:,} (CSV)</a>
      </div>
    </section>

    <section id="method" aria-labelledby="method-h">
      <h2 id="method-h">Method and sources</h2>
      <p>Statuses are restated exactly as ED published them. Earnings figures count each program once
        and use Truewise&rsquo;s undergraduate earnings-premium test.</p>
      <details class="more"><summary>How the figures were built</summary><ul>
        <li><b>The list.</b> ED&rsquo;s &ldquo;List of Institutions That Previously Submitted FVT/GE Data&rdquo;, attached to electronic announcement GENERAL-26-49 (11 August 2026), compiled {when}. It covers open colleges with at least one program, at the four-digit CIP level, meeting ED&rsquo;s minimum of 30 completers.</li>
        <li><b>In ED&rsquo;s words.</b> &ldquo;{esc(ED_COMPLETENESS)}&rdquo; And: {esc(ED_NOT_SUBMITTED)}</li>
        <li><b>The join.</b> By six-digit OPEID. {s["matched"]:,} of the {total:,} colleges have programs in the Scorecard data Truewise publishes.</li>
        <li><b>The fail rate.</b> Graduates&rsquo; median earnings against a typical high-school graduate in the state. Programs without enough data for a verdict are left out of all three rates.</li>
        <li><b>The adjustment.</b> For each sector and credential, the complete filers&rsquo; rate is applied to the other colleges&rsquo; programs and summed.</li>
      </ul></details>
      <ul class="srcs"><li>ED, <a href="https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2026-08-11/guidance-fvt/ge-data-reporting-stats-early-implementation-and-next-steps-publication">GENERAL-26-49</a> and <a href="https://fsapartners.ed.gov/sites/default/files/2026-08/FVTGEDataReportingFinal.xlsx">the spreadsheet</a></li>
        <li>College Scorecard, release 2026-06-10</li>
        <li>Reproduce: <code>published/fvtge_reporting.parquet</code>, <code>pipeline/build_fvtge.py</code></li></ul>
    </section>
  </main>
"""
    return (
        page_head
        + body
        + LOOKUP_SCRIPT.replace("__CSV__", csv_name)
        + FOOTER
        + BEACON
        + "</body>\n</html>\n"
    )


# Plain script, no template literals. institutions.json (about 90 KB compressed) is fetched on the
# first focus or keystroke, not on page load. Rows are [name, state, not_submitted, programs,
# judged, slug or 0]. No-result and error messages go to the live status region; a keyboard retry
# returns focus to the search field (Prototype A review, 27 September).
LOOKUP_SCRIPT = r"""  <script>
  (function () {
    var q = document.getElementById("lk-q"), list = document.getElementById("lk-rows"),
        status = document.getElementById("lk-status"), rows = null, loading = false, refocus = false;
    var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    var norm = function (s) { return String(s || "").toLowerCase().normalize("NFKD")
      .replace(/[^a-z0-9 ]/g, " ").replace(/ +/g, " ").trim(); };
    function row(d) {
      var name = d[5] ? '<a href="/college/' + esc(d[5]) + '/">' + esc(d[0]) + "</a>" : esc(d[0]);
      return '<li><span class="lookup__name">' + name + '</span>' +
        '<span class="lookup__meta">' + esc(d[1]) + " · Truewise earnings verdicts: " + d[4] +
        " program" + (d[4] === 1 ? "" : "s") + "</span>" +
        '<span class="lookup__count' + (d[2] === 0 ? " lookup__count--none" : "") + '"><b>' + d[2] +
        ' of 7</b>not submitted</span></li>';
    }
    function load() {
      if (loading || rows) return;
      loading = true;
      status.className = "lookup__status"; status.textContent = "Loading the list of colleges…";
      fetch("/findings/fvtge-reporting/institutions.json").then(function (r) {
        if (!r.ok) throw new Error(r.status); return r.json();
      }).then(function (d) {
        rows = d; loading = false; run();
        if (refocus) { refocus = false; q.focus(); }
      }).catch(function () {
        loading = false; status.className = "lookup__status lookup__status--error";
        status.innerHTML = "The college list did not load. " +
          '<button type="button" class="btn btn--secondary" id="lk-retry">Try again</button> ' +
          'or <a href="/findings/fvtge-reporting/__CSV__">download the CSV</a>.';
        document.getElementById("lk-retry").addEventListener("click", function () { refocus = true; load(); });
      });
    }
    function run() {
      if (!rows) { load(); return; }
      status.className = "lookup__status";
      var t = norm(q.value);
      if (t.length < 2) { list.innerHTML = "";
        status.textContent = "Type two or more letters of a college’s name."; return; }
      var hits = rows.filter(function (d) { return norm(d[0]).indexOf(t) !== -1; });
      if (!hits.length) { list.innerHTML = "";
        status.textContent = "No college on ED’s list matches “" + q.value +
          "”. Try a shorter part of the name, or check the spelling."; return; }
      list.innerHTML = hits.slice(0, 25).map(row).join("");
      status.textContent = hits.length > 25 ? "Showing 25 of " + hits.length + " matches. Keep typing to narrow it."
        : hits.length + " match" + (hits.length === 1 ? "" : "es") + ".";
    }
    q.addEventListener("focus", load);
    q.addEventListener("input", run);
  })();
  </script>
"""


def write_outputs(s, inst) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(render_page(s))
    # Compact rows, [name, state, not_submitted, programs, judged, slug or 0], for the search. Loaded
    # only when someone starts typing; field names per row tripled its size.
    (OUT_DIR / "institutions.json").write_text(
        json.dumps(
            [
                [
                    i["name"],
                    i["state"],
                    i["not_submitted"],
                    i["programs"],
                    i["judged"],
                    i["profile"][len("/college/") : -1] if i["profile"] else 0,
                ]
                for i in inst
            ],
            separators=(",", ":"),
        )
    )
    keys = [k for k, _ in COMPONENT_LABELS]
    with (OUT_DIR / f"fvtge-reporting-{s['compiled']}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "opeid6",
                "institution",
                "state",
                "sector",
                "components_not_submitted",
                *keys,
                "truewise_programs",
                "truewise_programs_with_verdict",
                "truewise_programs_failing",
                "truewise_profile",
                "status_as_of",
            ]
        )
        for i in inst:
            w.writerow(
                [
                    i["opeid6"],
                    i["name"],
                    i["state"],
                    i["sector"],
                    i["not_submitted"],
                    *[i["components"][k] for k in keys],
                    i["programs"],
                    i["judged"],
                    i["fail"],
                    f"{BASE}{i['profile']}" if i["profile"] else "",
                    s["compiled"],
                ]
            )


def main() -> None:
    con = _con()
    s = compute(con)
    write_outputs(s, institutions(con))
    print(
        f"FVT/GE finding: {s['missing']:,} of {s['total']:,} with a component not submitted "
        f"(as of {s['compiled']}); {s['matched']:,} matched to Scorecard data"
    )
    print(f"wrote -> {OUT_DIR}")


if __name__ == "__main__":
    main()
