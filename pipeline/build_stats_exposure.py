"""STATS grad-program exposure: which graduate programs are at risk under the final
Earnings Accountability (STATS) rule, framed as a reproducible framework + sensitivity range.

The rule (Federal Register 2026-07-01) judges GRADUATE programs against the LOWEST of three
bachelor's-holder earnings figures (Census, aged 25-34, not enrolled: same state, same field in state,
same field nationally), with a $1 threshold where field data is thin; 4th-year earnings; a program
that fails 2 of 3 consecutive years loses Direct Loan eligibility (effective 2027-07-01, first
losses possible 2028-29). ED has NOT yet published the exact bachelor's-holder threshold, and the
count of exposed programs is very sensitive to it, so we publish the whole exposure curve and a
plausible range rather than one headline number. Single most-recent snapshot: this is exposure on
current data, not a prediction of which programs will actually lose eligibility.

Writes /findings/stats-grad-exposure/ and a /findings/ index. Reuses value_check.parquet.

Usage:
    python -m pipeline.build_stats_exposure
"""

from __future__ import annotations

import duckdb

from pipeline.build_college_pages import BASE, BEACON, FOOTER, esc, head, money
from pipeline.config import PARQUET_DIR, ROOT
from pipeline.og_images import card as render_card
from pipeline.tokens_gen import BAD as OG_BAD

SITE = ROOT / "site"
GRAD_LEVELS = ("4", "5", "6", "7", "8")  # post-bacc cert, master's, doctoral, first-prof, grad cert
BENCHMARKS = [50000, 55000, 58000, 60000, 62000, 64000, 66000, 70000]
# Plausible bachelor's-holder benchmark band. Upper bound: NCES median earnings of 25-34 bachelor's
# holders working full-time year-round, $66,600 in 2022. Lower bound: the rule's broader "working"
# population (part-time included) runs below the full-time figure. See the citation on the page.
BAND = (58000, 66000)
REF = 60000  # illustrative reference benchmark for the breakdowns


def compute_exposure(con) -> dict:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con.execute(
        f"""CREATE OR REPLACE VIEW grad AS
        SELECT *, earnings_median_4yr AS earn FROM read_parquet('{vc}')
        WHERE credential_level IN {GRAD_LEVELS} AND regexp_matches(unitid, '^[0-9]+$')"""
    )
    total = con.sql("SELECT count(*) FROM grad").fetchone()[0]
    denom = con.sql("SELECT count(*) FROM grad WHERE earn IS NOT NULL").fetchone()[0]

    curve = []
    for b in BENCHMARKS:
        n = con.sql(f"SELECT count(*) FROM grad WHERE earn IS NOT NULL AND earn < {b}").fetchone()[
            0
        ]
        curve.append({"benchmark": b, "n_below": n, "pct": round(100 * n / denom, 1)})

    def _below(b):
        return con.sql(
            f"SELECT count(*) FROM grad WHERE earn IS NOT NULL AND earn < {b}"
        ).fetchone()[0]

    # Band range = [programs below the low benchmark, programs below the high benchmark].
    band = sorted([_below(BAND[0]), _below(BAND[1])])

    by_cred = con.sql(
        f"""SELECT credential_desc,
               count(*) FILTER (WHERE earn IS NOT NULL) AS with_earn,
               count(*) FILTER (WHERE earn IS NOT NULL AND earn < {REF}) AS below
            FROM grad GROUP BY credential_desc ORDER BY with_earn DESC"""
    ).fetchall()

    top_fields = con.sql(
        f"""SELECT rtrim(cip_desc, '. ') AS field, count(*) AS below,
               round(median(earn)) AS med
            FROM grad WHERE earn IS NOT NULL AND earn < {REF}
            GROUP BY field ORDER BY below DESC LIMIT 15"""
    ).fetchall()

    pct = con.sql(
        "SELECT round(quantile_cont(earn,0.10)), round(median(earn)), round(quantile_cont(earn,0.75)) "
        "FROM grad WHERE earn IS NOT NULL"
    ).fetchone()

    return {
        "total": total,
        "denom": denom,
        "curve": curve,
        "band": band,
        "by_cred": by_cred,
        "top_fields": top_fields,
        "p10": pct[0],
        "median": pct[1],
        "p75": pct[2],
    }


def render_page(s) -> str:
    canonical = f"{BASE}/findings/stats-grad-exposure/"
    lo, hi = s["band"]
    title = "How many graduate programs are exposed under the new earnings rule?"
    desc = (
        f"On the most recent federal data, {lo:,} to {hi:,} US graduate programs fall below a single "
        f"national bachelor's-holder earnings line. The final STATS rule uses field-level thresholds and "
        f"a $1 exemption, so the true count is likely lower. Reproducible, from federal data."
    )
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Findings","item":"{BASE}/findings/"}},
    {{"@type":"ListItem","position":2,"name":"Graduate-program exposure under STATS","item":"{canonical}"}}
  ]}}
  </script>
"""
    render_card(
        SITE / "og" / "findings" / "stats-grad-exposure.png",
        "Finding · federal earnings-accountability rule",
        "Which graduate programs are exposed?",
        big=f"{lo:,}-{hi:,}",
        big_color=OG_BAD,
        sub="Graduate programs below one national bachelor's line. Likely an overestimate.",
    )
    p = [head(title, desc, canonical, ld, og_image="/og/findings/stats-grad-exposure.png")]
    p.append('  <main class="wrap pg">\n')
    p.append(
        '    <nav class="crumbs"><a href="/findings/">Findings</a> &rsaquo; STATS graduate-program exposure</nav>\n'
    )
    p.append("    <h1>Which graduate programs are exposed under the new earnings rule?</h1>\n")
    p.append(
        f'    <div class="verdict">Against a single national bachelor\'s-holder earnings line of '
        f"<b>{money(BAND[0])}</b> to <b>{money(BAND[1])}</b>, <b>{lo:,} to {hi:,}</b> graduate programs "
        f"fall below it on the most recent earnings data, out of <b>{s['denom']:,}</b> with reported "
        f"four-year earnings (about 1 in 5 of {s['total']:,}; the rest are privacy-suppressed). "
        f"<b>Treat this as a likely overestimate.</b> The final rule does not hold graduate programs to one "
        f"national line: each is held to the lowest of three bachelor's-holder figures, and many get a $1 "
        f"threshold that exempts them. The true count is very likely lower, and we cannot yet say by how much.</div>\n"
    )
    p.append(
        '    <p class="src">This is <b>exposure on the most recent snapshot, not a prediction</b>. '
        "The rule fails a program only after two of three consecutive years below its threshold. ED has "
        "not published the thresholds; first results are expected in 2027. For scale, ED's own estimate "
        "in the final rule is about 3,302 programs failing in the first year across all programs, "
        "undergraduate and graduate together, under coverage rules that differ from this page's, so the "
        "two figures are not directly comparable.</p>\n"
    )

    # Exposure curve.
    p.append('    <h2 class="sec">Exposure by benchmark</h2>\n')
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Benchmark comparison"><table class="t"><thead><tr><th>Single national line</th>'
        '<th class="num">Grad programs below</th><th class="num">Share of grad programs with earnings</th>'
        "</tr></thead><tbody>\n"
    )
    for row in s["curve"]:
        inband = BAND[0] <= row["benchmark"] <= BAND[1]
        mark = ' style="background:var(--bg-alt)"' if inband else ""
        p.append(
            f"      <tr{mark}><td>{money(row['benchmark'])}"
            f"{' &nbsp;<b>(likely national figure)</b>' if inband else ''}</td>"
            f"<td class='num'>{row['n_below']:,}</td><td class='num'>{row['pct']}%</td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")
    p.append(
        f'    <p class="src">Grad-program four-year earnings run higher than undergraduate: median '
        f"<b>{money(s['median'])}</b> (10th percentile {money(s['p10'])}, 75th {money(s['p75'])}). "
        "The high-school-graduate benchmark used for undergraduate programs is about $36,082; graduate "
        "programs are held to the higher bachelor's-holder line instead.</p>\n"
    )

    # By credential.
    p.append(
        f'    <h2 class="sec">By credential (at an illustrative {money(REF)} benchmark)</h2>\n'
    )
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Coverage by credential"><table class="t"><thead><tr><th>Credential</th><th class="num">With reported earnings</th>'
        '<th class="num">Below benchmark</th></tr></thead><tbody>\n'
    )
    for cred, with_earn, below in s["by_cred"]:
        p.append(
            f"      <tr><td>{esc(cred)}</td><td class='num'>{with_earn:,}</td>"
            f"<td class='num'>{below:,}</td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")

    # Top exposed fields.
    p.append(
        f'    <h2 class="sec">Fields with the most programs below a national {money(REF)} line</h2>\n'
    )
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Coverage by field of study"><table class="t"><thead><tr><th>Field of study</th>'
        '<th class="num">Programs below</th><th class="num">Median earnings</th></tr></thead><tbody>\n'
    )
    for field, below, med in s["top_fields"]:
        p.append(
            f"      <tr><td>{esc(field)}</td><td class='num'>{below:,}</td>"
            f"<td class='num'>{money(med)}</td></tr>\n"
        )
    p.append("    </tbody></table></div>\n")
    p.append(
        '    <p class="src"><b>Read this list with more caution than anything else on this page.</b> '
        "Where the data allows, the rule compares a graduate program with bachelor's holders in the same "
        "field, and bachelor's holders in teaching, counseling, social work and the arts also earn "
        f"modestly. For these fields the real threshold is likely well below {money(REF)}, so many of "
        "these programs would pass. The list shows where graduate earnings are low in absolute terms, "
        "not which programs will fail.</p>\n"
    )

    # Method + caveats.
    p.append('    <h2 class="sec">Method and caveats</h2>\n')
    p.append(
        "    <ul>\n"
        f"      <li><b>Who is counted.</b> Graduate programs (post-baccalaureate certificate, master's, "
        f"doctoral, first-professional, and graduate certificate) with a reported four-year median "
        f"earnings figure: {s['denom']:,} of {s['total']:,}. The rest are privacy-suppressed and never "
        "guessed.</li>\n"
        "      <li><b>What the rule actually compares against.</b> For a graduate program the threshold "
        "is Census median earnings of working bachelor's-degree holders aged 25 to 34 who were not "
        "enrolled, taking the <b>lowest</b> of three figures: the state where the institution is located, "
        "the same field of study in that state, or the same field nationally. National figures replace "
        "state ones when most of an institution's students come from out of state. Where same-state, "
        "same-field data is too thin, the threshold is set to <b>$1</b>, which ED estimates exempts about "
        "2,650 graduate programs.</li>\n"
        "      <li><b>What this page applies instead.</b> One figure, a national bachelor's-holder median. "
        "NCES puts it at <b>$66,600</b> for full-time year-round workers (2022), and the rule's broader "
        "working population runs lower, hence the $58,000 to $66,000 band. This page does not apply the "
        "same-field comparison or the $1 exemption, because the field-level Census figures are not in "
        "this dataset. The exemption can only reduce the count, and the field comparison lowers most "
        "thresholds, especially in modestly paid fields and lower-earning states. It can raise one in a "
        "high-earning state and field, so the range is a likely overestimate rather than a strict "
        "ceiling.</li>\n"
        "      <li><b>The horizon.</b> Earnings are median earnings in the fourth tax year after "
        "completing, the same measure the rule uses.</li>\n"
        "      <li><b>Not a verdict.</b> A program only loses Direct Loan eligibility after failing two of "
        "three consecutive years. This is exposure on one recent snapshot, an early-warning picture, not a "
        "list of programs that will lose funding.</li>\n"
        "    </ul>\n"
    )
    p.append(
        '    <p class="repro">Reproduce this: graduate rows of <code>value_check.parquet</code> '
        "(credential levels 4 to 8) with <code>earnings_median_4yr</code> below the benchmark. Script: "
        "<code>pipeline/build_stats_exposure.py</code>. Full method: "
        '<a href="/methodology/">methodology</a>. Sources: U.S. Department of Education College Scorecard '
        "(release 2026-06-10); the final STATS / Earnings Accountability rule (Federal Register, "
        "2026-07-01).</p>\n"
    )
    p.append(
        '    <div class="cta-row"><a class="primary" href="/data/value_check.parquet" download>'
        "Download the dataset &darr;</a></div>\n"
    )
    p.append("  </main>\n")
    p.append(FOOTER)
    p.append(BEACON)
    p.append("</body>\n</html>\n")
    return "".join(p)


# The findings this module publishes, as directory names under site/findings/. This is the
# authoritative list: pipeline/prune_orphans.py checks the built tree against it, so a retired
# finding cannot linger on disk and ship from a local deploy (site/findings/data-audit/ did).
PUBLISHED_FINDINGS = ("stats-grad-exposure",)


def render_index() -> str:
    canonical = f"{BASE}/findings/"
    title = "Findings: reproducible numbers from US education data"
    desc = (
        "Truewise findings: each a reproducible number from public federal education data, with the "
        "method and the dataset behind it."
    )
    p = [head(title, desc, canonical)]
    p.append('  <main class="wrap pg">\n')
    p.append('    <nav class="crumbs">Findings</nav>\n')
    p.append("    <h1>Findings</h1>\n")
    p.append(
        '    <p class="idline">Each finding is a reproducible number from public federal data, with '
        "its method and dataset. Corrections welcome.</p>\n"
    )
    p.append('    <ul class="schoollist">\n')
    p.append(
        '      <li><a href="/findings/stats-grad-exposure/">Which graduate programs are exposed under '
        'the new earnings rule?</a><div class="meta">How many graduate programs fall below a national '
        "bachelor's-holder earnings line, and why the rule's field-level test means the true count is "
        "likely lower.</div></li>\n"
    )
    p.append("    </ul>\n")
    p.append("  </main>\n")
    p.append(FOOTER)
    p.append(BEACON)
    p.append("</body>\n</html>\n")
    return "".join(p)


def main() -> None:
    con = duckdb.connect()
    s = compute_exposure(con)
    out = SITE / "findings" / PUBLISHED_FINDINGS[0]
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_page(s))
    (SITE / "findings" / "index.html").write_text(render_index())
    lo, hi = s["band"]
    print(
        f"STATS exposure: {s['denom']:,} grad programs with earnings; likely band {lo:,}-{hi:,} exposed"
    )
    print(f"wrote -> {SITE / 'findings'}")


if __name__ == "__main__":
    main()
