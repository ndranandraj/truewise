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

from pipeline.build_college_pages import BASE, BEACON, FOOTER, esc, head
from pipeline.config import ROOT
from pipeline.og_images import card as render_card
from pipeline.program_unit import programs_sql
from pipeline.tokens_gen import BAD as OG_BAD

SITE = ROOT / "site"
PUBLISHED = ROOT / "published"
SLUG = "fvtge-reporting"
OUT_DIR = SITE / "findings" / SLUG

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


def render_page(s) -> str:
    canonical = f"{BASE}/findings/{SLUG}/"
    when = _date(s["compiled"])
    a = s["assoc"]
    r_miss = 100 * a["fail_missing"] / a["n_missing"]
    r_comp = 100 * a["fail_complete"] / a["n_complete"]
    r_exp = 100 * a["expected_missing"]
    title = "Which colleges had not filed their federal earnings-transparency data?"
    desc = (
        f"As of {when}, the Department of Education listed {s['missing']:,} of {s['total']:,} colleges as "
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
        big=f"{s['missing']:,} of {s['total']:,}",
        big_color=OG_BAD,
        sub=f"{s['none_filed']:,} had submitted no file at all.",
    )
    p = [head(title, desc, canonical, ld, og_image=f"/og/findings/{SLUG}.png")]
    p.append('  <main class="wrap pg">\n')
    p.append(
        '    <nav class="crumbs"><a href="/findings/">Findings</a> &rsaquo; FVT/GE reporting status</nav>\n'
    )
    p.append(f"    <h1>{esc(title)}</h1>\n")
    p.append(
        f'    <div class="verdict">As of <b>{when}</b>, the U.S. Department of Education listed '
        f"<b>{s['missing']:,}</b> of <b>{s['total']:,}</b> colleges ({_pct(s['missing'], s['total'])}%) as "
        "not having submitted at least one of the seven FVT/GE file components required for the 2024 "
        f"and 2025 reporting cycles. <b>{s['none_filed']:,}</b> had submitted no file at all, including "
        f"<b>{s['all7']:,}</b> with all seven components marked not submitted (the others had some "
        "components marked not required). The Department intends to publish program-level data and "
        "statistics derived from these files in 2027. A new rule replaces the FVT/GE rule on 1 July "
        "2027.</div>\n"
    )
    p.append(
        '    <p class="src"><b>What the list does and does not say.</b> In the Department’s words: '
        f"“{esc(ED_COMPLETENESS)}” And: {esc(ED_NOT_SUBMITTED)} Files the Department rejected "
        "with errors count as not submitted. Colleges have until <b>15 January 2027</b> to submit anything "
        "missing from the 2024 and 2025 cycles; the 2026 cycle is due <b>1 October 2026</b>. Filings made "
        f"after {when} are not reflected here.</p>\n"
    )

    # By sector.
    p.append('    <h2 class="sec">By sector</h2>\n')
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Reporting status by sector">'
        '<table class="t"><thead><tr><th>Sector</th><th class="num">Colleges listed</th>'
        '<th class="num">At least one not submitted</th><th class="num">Submitted no file</th></tr></thead><tbody>\n'
    )
    for x in s["sectors"]:
        p.append(
            f"      <tr><td>{esc(SECTOR_LABEL.get(x['sector'], x['sector']))}</td>"
            f"<td class='num'>{x['n']:,}</td>"
            f"<td class='num'>{x['missing']:,} ({_pct(x['missing'], x['n'])}%)</td>"
            f"<td class='num'>{x['none_filed']:,}</td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")

    # By component.
    p.append('    <h2 class="sec">Which files are missing</h2>\n')
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Reporting status by file">'
        '<table class="t"><thead><tr><th>Required component</th><th class="num">Not submitted</th>'
        '<th class="num">Not required</th></tr></thead><tbody>\n'
    )
    for c in s["components"]:
        p.append(
            f"      <tr><td>{esc(c['label'])}</td><td class='num'>{c['not_submitted']:,}</td>"
            f"<td class='num'>{c['not_required']:,}</td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")
    p.append(
        '    <p class="src">“Not required” is the Department’s own status: for example, a '
        "college that was not operating that year, or had no program large enough to report.</p>\n"
    )

    # Association.
    p.append('    <h2 class="sec">What the Scorecard shows about these colleges</h2>\n')
    p.append(
        f"    <p>Using the College Scorecard earnings Truewise already publishes (not the FVT/GE files "
        f"themselves), programs at colleges with at least one file not submitted fail the earnings "
        f"test more often: <b>{r_miss:.1f}%</b> of their programs with an earnings verdict, against "
        f"<b>{r_comp:.1f}%</b> at colleges that had submitted everything required.</p>\n"
    )
    p.append(
        f"    <p>Part of that gap is who these colleges are. They are more often for-profit and offer "
        f"more certificates, where fail rates are higher everywhere. Holding sector and credential "
        f"fixed, the complete filers’ rates would predict <b>{r_exp:.1f}%</b> for the colleges "
        f"with files not submitted. The actual figure is <b>{r_miss:.1f}%</b>, so about "
        f"{r_miss - r_exp:.0f} points of the gap remain after that adjustment.</p>\n"
    )
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Fail rate by sector and credential">'
        '<table class="t"><thead><tr><th>Sector and credential</th>'
        '<th class="num">Fail rate, a file not submitted</th><th class="num">Fail rate, all submitted</th>'
        "</tr></thead><tbody>\n"
    )
    for c in s["cells"]:
        rm = 100 * c["fail_missing"] / c["n_missing"]
        rc = 100 * c["fail_complete"] / c["n_complete"]
        p.append(
            f"      <tr><td>{esc(c['sector'])}, {esc(CRED_LABEL[c['cred']].lower())}</td>"
            f"<td class='num'>{rm:.1f}% <span class='meta'>of {c['n_missing']:,}</span></td>"
            f"<td class='num'>{rc:.1f}% <span class='meta'>of {c['n_complete']:,}</span></td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")
    p.append(
        '    <p class="src"><b>This is an association, not an explanation.</b> It does not show that a '
        "missing file hides worse results, or that any college’s data is incomplete. It says that, in "
        "public Scorecard data, the programs at these colleges have tended to leave graduates earning "
        "less relative to a high-school graduate.</p>\n"
    )

    # By state.
    p.append('    <h2 class="sec">By state</h2>\n')
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Reporting status by state">'
        '<table class="t"><thead><tr><th>State</th><th class="num">Colleges listed</th>'
        '<th class="num">At least one not submitted</th><th class="num">Submitted no file</th></tr></thead><tbody>\n'
    )
    for x in s["states"]:
        label = "Foreign institutions" if x["state"] == "FC" else x["state"]
        p.append(
            f"      <tr><td>{esc(label)}</td><td class='num'>{x['n']:,}</td>"
            f"<td class='num'>{x['missing']:,} ({_pct(x['missing'], x['n'])}%)</td>"
            f"<td class='num'>{x['none_filed']:,}</td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")

    # Institution search.
    p.append('    <h2 class="sec" id="search">Look up a college</h2>\n')
    p.append(
        '    <label class="field-label" for="fv-q">Search the Department’s list by name</label>\n'
        '    <div class="searchbox"><input id="fv-q" type="search" autocomplete="off" '
        'placeholder="e.g. Palomar" aria-describedby="fv-status" /></div>\n'
        '    <p class="idline" id="fv-status" role="status" aria-live="polite">Type two or more letters.</p>\n'
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Colleges on the Department’s list">'
        '<table class="t"><thead><tr><th>College</th><th>State</th>'
        '<th class="num">Components not submitted</th><th class="num">Programs Truewise can assess</th>'
        '</tr></thead><tbody id="fv-rows"></tbody></table></div>\n'
        '    <noscript><p class="src">Searching needs JavaScript. Every college on the list is in the '
        "CSV below.</p></noscript>\n"
    )
    csv_name = f"fvtge-reporting-{s['compiled']}.csv"
    p.append(
        f'    <div class="cta-row"><a class="btn" href="/findings/{SLUG}/{csv_name}" download>'
        "Download every college on the list (CSV) &darr;</a></div>\n"
    )

    # Method.
    p.append('    <h2 class="sec">Method and sources</h2>\n')
    p.append(
        "    <ul>\n"
        f"      <li><b>The list.</b> The Department’s “List of Institutions That Previously "
        f"Submitted FVT/GE Data”, attached to electronic announcement GENERAL-26-49 (11 August 2026) "
        f"and compiled on {when}. It covers open colleges with at least one program, at the four-digit CIP "
        "level, that meets the Department’s minimum of 30 completers; statuses are restated here exactly as the Department published them.</li>\n"
        f"      <li><b>The join.</b> By six-digit OPEID. {s['matched']:,} of the {s['total']:,} colleges on "
        "the list have programs in the College Scorecard data Truewise publishes.</li>\n"
        "      <li><b>The fail rate.</b> The earnings-premium test Truewise applies to every program: "
        "graduates’ median earnings against a typical high-school graduate in the state. Programs "
        "without enough data for a verdict are excluded from both rates.</li>\n"
        "      <li><b>The adjustment.</b> For each sector and credential, the complete filers’ fail "
        "rate is applied to the number of programs at colleges with files not submitted, and summed.</li>\n"
        "    </ul>\n"
    )
    p.append(
        '    <p class="repro">Reproduce this: <code>published/fvtge_reporting.parquet</code> (built from '
        "the Department’s spreadsheet by <code>pipeline/build_fvtge_source.py</code>) joined to "
        "<code>value_check.parquet</code> by <code>pipeline/build_fvtge.py</code>. Sources: "
        '<a href="https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements/2026-08-11/'
        'guidance-fvt/ge-data-reporting-stats-early-implementation-and-next-steps-publication">'
        "GENERAL-26-49</a>; "
        '<a href="https://fsapartners.ed.gov/sites/default/files/2026-08/FVTGEDataReportingFinal.xlsx">'
        "the Department’s spreadsheet</a>; College Scorecard (release 2026-06-10).</p>\n"
    )
    p.append("  </main>\n")
    p.append(SEARCH_SCRIPT)
    p.append(FOOTER)
    p.append(BEACON)
    p.append("</body>\n</html>\n")
    return "".join(p)


# Plain script, no template literals: nothing in it can be broken by a comment containing a
# backtick. Reads institutions.json from the same directory.
SEARCH_SCRIPT = """  <script>
  (function () {
    var q = document.getElementById("fv-q"), rows = document.getElementById("fv-rows"),
        status = document.getElementById("fv-status"), data = null, t;
    var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    var norm = function (s) { return String(s || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9 ]/g, " ").replace(/ +/g, " ").trim(); };
    function draw() {
      var term = norm(q.value);
      if (term.length < 2) { rows.innerHTML = ""; status.textContent = "Type two or more letters."; return; }
      var hits = data.filter(function (d) { return norm(d[0]).indexOf(term) !== -1; });
      var shown = hits.slice(0, 50);
      rows.innerHTML = shown.map(function (d) {
        var name = d[5] ? '<a href="/college/' + esc(d[5]) + '/">' + esc(d[0]) + "</a>" : esc(d[0]);
        var assess = d[3] ? d[4] + " of " + d[3] : "none in Scorecard data";
        return "<tr><td>" + name + "</td><td>" + esc(d[1]) + "</td><td class=\\"num\\">" +
          d[2] + " of 7</td><td class=\\"num\\">" + assess + "</td></tr>";
      }).join("");
      status.textContent = hits.length ? (hits.length > 50 ? "Showing 50 of " + hits.length + " matches." : hits.length + (hits.length === 1 ? " match." : " matches.")) : "No college on the list matches that name.";
    }
    q.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () {
        if (data) return draw();
        fetch("institutions.json").then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (j) { data = j; draw(); },
                function () { status.textContent = "The list did not load. Every college is in the CSV below."; });
      }, 150);
    });
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
