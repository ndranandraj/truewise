"""STATS grad-program exposure: which graduate programs are at risk under the final
Earnings Accountability (STATS) rule, framed as a reproducible framework + sensitivity range.

The rule (Federal Register 2026-07-01) judges GRADUATE programs against a bachelor's-degree-
holder earnings benchmark (Census, BA holders aged 25-34), using 4th-year earnings; a program
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

SITE = ROOT / "site"
GRAD_LEVELS = ("4", "5", "6", "7", "8")  # post-bacc cert, master's, doctoral, first-prof, grad cert
BENCHMARKS = [45000, 50000, 55000, 60000, 62000, 65000, 70000]
BAND = (55000, 62000)  # plausible bachelor's-holder benchmark band (see Census anchor in the page)
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
        f"Under the final STATS earnings-accountability rule, roughly {lo:,} to {hi:,} US graduate "
        f"programs would fall below a typical bachelor's-holder's earnings on the most recent data, "
        f"mostly master's degrees in teaching, counseling, and the arts. Reproducible, from federal data."
    )
    ld = f"""  <script type="application/ld+json">
  {{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[
    {{"@type":"ListItem","position":1,"name":"Findings","item":"{BASE}/findings/"}},
    {{"@type":"ListItem","position":2,"name":"Graduate-program exposure under STATS","item":"{canonical}"}}
  ]}}
  </script>
"""
    p = [head(title, desc, canonical, ld)]
    p.append('  <main class="wrap pg">\n')
    p.append(
        '    <nav class="crumbs"><a href="/findings/">Findings</a> &rsaquo; STATS graduate-program exposure</nav>\n'
    )
    p.append("    <h1>Which graduate programs are exposed under the new earnings rule?</h1>\n")
    p.append(
        f'    <div class="verdict">Depending on where the Department of Education sets the '
        f"bachelor's-holder benchmark, likely between <b>{money(BAND[0])}</b> and <b>{money(BAND[1])}</b> "
        f"based on Census data, roughly <b>{lo:,} to {hi:,}</b> graduate programs would fall below it "
        f"on the most recent earnings data. That is out of <b>{s['denom']:,}</b> graduate programs with "
        f"reported four-year earnings (about 1 in 5 of {s['total']:,}; the rest are privacy-suppressed).</div>\n"
    )
    p.append(
        '    <p class="src">This is <b>exposure on the most recent snapshot, not a prediction</b>. '
        "The rule fails a program only after two of three consecutive years below the line, and ED "
        "has not yet published the exact benchmark. We publish the whole curve so the number updates "
        "the moment ED sets it.</p>\n"
    )

    # Exposure curve.
    p.append('    <h2 class="sec">Exposure by benchmark</h2>\n')
    p.append(
        '    <table class="t"><thead><tr><th>Bachelor\'s-holder benchmark</th>'
        '<th class="num">Grad programs below</th><th class="num">Share of grad programs with earnings</th>'
        "</tr></thead><tbody>\n"
    )
    for row in s["curve"]:
        inband = BAND[0] <= row["benchmark"] <= BAND[1]
        mark = ' style="background:var(--bg-alt)"' if inband else ""
        p.append(
            f"      <tr{mark}><td>{money(row['benchmark'])}"
            f"{' &nbsp;<b>(likely range)</b>' if inband else ''}</td>"
            f"<td class='num'>{row['n_below']:,}</td><td class='num'>{row['pct']}%</td></tr>\n"
        )
    p.append("    </tbody></table>\n")
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
        '    <table class="t"><thead><tr><th>Credential</th><th class="num">With reported earnings</th>'
        '<th class="num">Below benchmark</th></tr></thead><tbody>\n'
    )
    for cred, with_earn, below in s["by_cred"]:
        p.append(
            f"      <tr><td>{esc(cred)}</td><td class='num'>{with_earn:,}</td>"
            f"<td class='num'>{below:,}</td></tr>\n"
        )
    p.append("    </tbody></table>\n")

    # Top exposed fields.
    p.append(
        f'    <h2 class="sec">Fields with the most exposed programs (below {money(REF)})</h2>\n'
    )
    p.append(
        '    <table class="t"><thead><tr><th>Field of study</th>'
        '<th class="num">Programs below</th><th class="num">Median earnings</th></tr></thead><tbody>\n'
    )
    for field, below, med in s["top_fields"]:
        p.append(
            f"      <tr><td>{esc(field)}</td><td class='num'>{below:,}</td>"
            f"<td class='num'>{money(med)}</td></tr>\n"
        )
    p.append("    </tbody></table>\n")
    p.append(
        '    <p class="src">These are the classic high-debt, modest-pay graduate fields: master\'s '
        "degrees in teaching, counseling, psychology, social work, and the arts.</p>\n"
    )

    # Method + caveats.
    p.append('    <h2 class="sec">Method and caveats</h2>\n')
    p.append(
        "    <ul>\n"
        f"      <li><b>Who is counted.</b> Graduate programs (post-baccalaureate certificate, master's, "
        f"doctoral, first-professional, and graduate certificate) with a reported four-year median "
        f"earnings figure: {s['denom']:,} of {s['total']:,}. The rest are privacy-suppressed and never "
        "guessed.</li>\n"
        "      <li><b>The benchmark.</b> The rule compares graduate programs to the median earnings of a "
        "working bachelor's-degree holder aged 25 to 34. ED has not published the exact figure. Census "
        "and NCES put bachelor's-holder earnings for that age group at roughly $60,000 to $62,000 "
        "(full-time, year-round); the rule's broader 'working' population likely runs somewhat lower, so "
        "we show a $55,000 to $62,000 likely band and the full curve.</li>\n"
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
        'the new earnings rule?</a><div class="meta">The STATS rule holds graduate programs to a '
        "bachelor's-holder earnings line; here is the reproducible exposure range.</div></li>\n"
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
    out = SITE / "findings" / "stats-grad-exposure"
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
