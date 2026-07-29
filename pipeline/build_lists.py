"""Generate ranked list pages: /lists/<slug>/ plus per-state "best value" lists.

These target the highest-volume search format in this category ("highest paying majors",
"best value colleges in Texas") while staying honest: every list ranks on ONE stated metric,
with its denominator and minimum-sample rule printed on the page. No weighted opinion index,
no composite score. Each row links to the underlying college or major page.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_lists
"""

from __future__ import annotations

import csv
import html
import io
import json as _j
import re

import duckdb

from pipeline.build_college_pages import (
    BASE,
    BEACON,
    FOOTER,
    STATE_NAMES,
    build_slugs,
    esc,
    head,
    money,
    qualifying_schools,
    slugify,
)
from pipeline.build_site import build_model
from pipeline.config import PARQUET_DIR, ROOT

SITE = ROOT / "site"
MIN_PROGRAMS = 10  # a major needs this many reported programs to be ranked
MIN_SCHOOL_PROGRAMS = 10  # a school needs this many decided programs to be ranked
TOP_N = 25


def _views(con) -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con.execute(
        f"""CREATE OR REPLACE VIEW p AS SELECT * FROM read_parquet('{vc}')
            WHERE regexp_matches(unitid, '^[0-9]+$')"""
    )
    con.execute(
        """CREATE OR REPLACE VIEW sch AS
        SELECT unitid, any_value(inst_name) AS nm, any_value(state) AS st,
               count(*) FILTER (WHERE value_flag != 'insufficient_data') AS n_dec,
               count(*) FILTER (WHERE value_flag = 'passes_earnings_premium') AS n_pass,
               median(earnings) AS med_earn, median(debt_payback_years) AS med_payback
        FROM p GROUP BY unitid"""
    )


def _strip_tags(cell) -> str:
    """Plain text for a CSV cell: drop markup, decode the few entities we emit."""
    txt = re.sub(r"<[^>]*>", "", str(cell))
    return html.unescape(txt).strip()


def _csv_text(headers, rows) -> str:
    """Build the CSV from the same rows the table renders, so the two cannot disagree."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["rank", *[_strip_tags(h) for h in headers]])
    for i, cells in enumerate(rows, 1):
        w.writerow([i, *[_strip_tags(c) for c in cells]])
    return buf.getvalue()


def _download_block(slug, headers, rows) -> str:
    """A client-side CSV download button. No server, no tracking, no new data."""
    payload = _j.dumps(_csv_text(headers, rows))
    fname = f"truewise-{slug}-scorecard-2026-06-10.csv"
    return (
        f'    <script type="application/json" id="csv-data">{payload}</script>\n'
        '    <p class="dl"><button type="button" id="dl-csv" class="dl-btn">Download this table (CSV)</button>'
        '<span class="dl-note"> Free to reuse with attribution (CC BY 4.0).</span></p>\n'
        "    <script>\n"
        "    (function () {\n"
        '      var el = document.getElementById("csv-data"), btn = document.getElementById("dl-csv");\n'
        "      if (!el || !btn) return;\n"
        '      btn.addEventListener("click", function () {\n'
        '        var blob = new Blob([JSON.parse(el.textContent)], { type: "text/csv;charset=utf-8" });\n'
        '        var a = document.createElement("a");\n'
        "        a.href = URL.createObjectURL(blob);\n"
        f'        a.download = "{fname}";\n'
        "        document.body.appendChild(a); a.click(); document.body.removeChild(a);\n"
        "        setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);\n"
        "      });\n"
        "    })();\n"
        "    </script>\n"
    )


def _page(title, desc, canonical, h1, lede, headers, rows, note, slug) -> str:
    p = [head(title, desc, canonical)]
    p.append('  <main class="wrap pg">\n')
    p.append(f'    <nav class="crumbs"><a href="/lists/">Lists</a> &rsaquo; {esc(h1)}</nav>\n')
    p.append(f"    <h1>{esc(h1)}</h1>\n")
    p.append(f'    <p class="idline">{lede}</p>\n')
    p.append('    <table class="t"><thead><tr><th class="num">#</th>')
    num_attr = " class='num'"
    for i, hd in enumerate(headers):
        p.append("<th" + (num_attr if i else "") + ">" + esc(hd) + "</th>")
    p.append("</tr></thead><tbody>\n")
    for i, cells in enumerate(rows, 1):
        p.append(f"      <tr><td class='num'>{i}</td>")
        for j, c in enumerate(cells):
            p.append("<td" + (num_attr if j else "") + ">" + str(c) + "</td>")
        p.append("</tr>\n")
    p.append("    </tbody></table>\n")
    p.append(_download_block(slug, headers, rows))
    p.append(f'    <p class="src">{note}</p>\n')
    p.append(
        '    <p class="src">Source: U.S. Department of Education College Scorecard (release '
        "2026-06-10). Earnings are median earnings of graduates measured up to four years after "
        "completing, and describe past graduates rather than a promise. Method: "
        '<a href="/methodology/">methodology</a>. '
        '<a href="https://github.com/ndranandraj/truewise/issues/new?labels=correction&title=Correction">'
        "Report an error</a>.</p>\n"
    )
    p.append("  </main>\n")
    p.append(FOOTER)
    p.append(BEACON)
    p.append("</body>\n</html>\n")
    return "".join(p)


def _major_link(field, cip_slugs):
    slug = cip_slugs.get(field)
    return f'<a href="/majors/{slug}/">{esc(field)}</a>' if slug else esc(field)


def build_major_lists(con, cip_slugs) -> list[tuple[str, str, str]]:
    """National major lists. Returns (slug, h1, meta-description) for the index."""
    out = []

    def rows_for(sql):
        return con.sql(sql).fetchall()

    # 1. Highest-paying majors (bachelor's).
    r = rows_for(f"""
        SELECT rtrim(cip_desc,'. ') AS field, round(median(earnings)) AS med, count(*) AS n
        FROM p WHERE credential_level='3' AND value_flag != 'insufficient_data'
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} ORDER BY med DESC LIMIT {TOP_N}""")
    out.append(
        (
            "highest-paying-majors",
            "Highest-paying college majors (bachelor's degree)",
            _page(
                "Highest-paying college majors, ranked by median earnings",
                "The bachelor's degree majors whose graduates earn the most, ranked by median "
                "earnings from federal data. Every figure links to the full major page.",
                f"{BASE}/lists/highest-paying-majors/",
                "Highest-paying college majors",
                "Bachelor's degree majors ranked by the median earnings of graduates, measured up "
                "to four years after finishing.",
                ["Major", "Median earnings", "Programs"],
                [(_major_link(f, cip_slugs), money(m), f"{n:,}") for f, m, n in r],
                f"Ranked on one number: the median of program-level median earnings for that major. "
                f"Majors need at least {MIN_PROGRAMS} programs with reported earnings to appear, so "
                "small or heavily suppressed fields are excluded rather than shown on thin data.",
                "highest-paying-majors",
            ),
        )
    )

    # 2. Lowest-paying majors (bachelor's).
    r = rows_for(f"""
        SELECT rtrim(cip_desc,'. ') AS field, round(median(earnings)) AS med, count(*) AS n
        FROM p WHERE credential_level='3' AND value_flag != 'insufficient_data'
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} ORDER BY med ASC LIMIT {TOP_N}""")
    out.append(
        (
            "lowest-paying-majors",
            "Lowest-paying college majors (bachelor's degree)",
            _page(
                "Lowest-paying college majors, ranked by median earnings",
                "The bachelor's degree majors whose graduates earn the least, from federal data, "
                "with the number of programs behind each figure.",
                f"{BASE}/lists/lowest-paying-majors/",
                "Lowest-paying college majors",
                "Bachelor's degree majors ranked from the lowest median graduate earnings up. Low "
                "pay is not the same as low value, but it is worth knowing before borrowing.",
                ["Major", "Median earnings", "Programs"],
                [(_major_link(f, cip_slugs), money(m), f"{n:,}") for f, m, n in r],
                f"Ranked on the median of program-level median earnings, majors with at least "
                f"{MIN_PROGRAMS} reported programs. Earnings are measured a few years after "
                "finishing, so fields where graduates commonly continue to further study can look "
                "lower here than their long-run pay.",
                "lowest-paying-majors",
            ),
        )
    )

    # 3. Fastest debt payback (bachelor's).
    r = rows_for(f"""
        SELECT rtrim(cip_desc,'. ') AS field, round(median(debt_payback_years),1) AS pb, count(*) AS n
        FROM p WHERE credential_level='3' AND debt_payback_years IS NOT NULL
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} ORDER BY pb ASC LIMIT {TOP_N}""")
    out.append(
        (
            "fastest-debt-payback-majors",
            "Majors that pay off their debt fastest",
            _page(
                "College majors that pay off student debt fastest",
                "Ranked by how many years of the earnings premium over a high-school graduate it "
                "takes to cover typical borrowing. Federal data.",
                f"{BASE}/lists/fastest-debt-payback-majors/",
                "Majors that pay off their debt fastest",
                "How long the earnings premium over a typical high-school graduate takes to recoup "
                "what graduates typically borrowed, lowest first.",
                ["Major", "Years to pay back", "Programs"],
                [(_major_link(f, cip_slugs), f"{pb:g} yrs", f"{n:,}") for f, pb, n in r],
                "Payback is median federal debt divided by the yearly earnings premium over a "
                "typical high-school graduate. It is a plain ratio, not the amortized federal "
                "debt-to-earnings rate, and it ignores interest and time to degree.",
                "fastest-debt-payback-majors",
            ),
        )
    )

    # 4. Fields where debt most often does not pay back.
    r = rows_for(f"""
        SELECT rtrim(cip_desc,'. ') AS field, count(*) AS n,
               round(median(debt_median)) AS debt, round(median(earnings)) AS earn
        FROM p WHERE value_flag='fails_earnings_premium' AND debt_median IS NOT NULL
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} ORDER BY n DESC LIMIT {TOP_N}""")
    out.append(
        (
            "programs-where-debt-does-not-pay-back",
            "Fields with the most programs where debt does not pay back",
            _page(
                "Where student debt does not pay back, by field of study",
                "Fields with the most programs whose graduates earn less than a typical "
                "high-school graduate while still carrying debt. Federal data.",
                f"{BASE}/lists/programs-where-debt-does-not-pay-back/",
                "Where debt does not pay back",
                "Fields with the most programs whose graduates both fall short of a typical "
                "high-school graduate's earnings and carry federal debt.",
                ["Field of study", "Programs", "Median debt", "Median earnings"],
                [(_major_link(f, cip_slugs), f"{n:,}", money(d), money(e)) for f, n, d, e in r],
                "Counted across all credential levels: programs flagged as falling short of the "
                "state high-school-graduate earnings benchmark that also report median debt. A "
                "program appearing here is a signal to ask questions, not a verdict on any student.",
                "programs-where-debt-does-not-pay-back",
            ),
        )
    )
    return out


def build_state_lists(con, slugs_by_unitid) -> list[tuple[str, str, str]]:
    """Per-state 'colleges whose graduates clear the bar most often' lists."""
    out = []
    states = [
        r[0]
        for r in con.sql(
            f"""SELECT st FROM sch WHERE n_dec >= {MIN_SCHOOL_PROGRAMS} AND st IS NOT NULL
                GROUP BY st HAVING count(*) >= 5 ORDER BY st"""
        ).fetchall()
    ]
    for st in states:
        rows = con.sql(f"""
            SELECT unitid, nm, n_dec, round(100.0*n_pass/n_dec) AS pass_pct, round(med_earn) AS med
            FROM sch WHERE st='{st}' AND n_dec >= {MIN_SCHOOL_PROGRAMS}
            ORDER BY pass_pct DESC, med DESC LIMIT {TOP_N}""").fetchall()
        st_name = STATE_NAMES.get(st, st)
        cells = []
        for unitid, nm, n_dec, pct, med in rows:
            slug = slugs_by_unitid.get(unitid)
            link = f'<a href="/college/{slug}/">{esc(nm)}</a>' if slug else esc(nm)
            cells.append((link, f"{pct:g}%", money(med), f"{n_dec:,}"))
        out.append(
            (
                f"best-value-colleges-{st.lower()}",
                f"Colleges in {st_name} whose graduates most often out-earn a high-school graduate",
                _page(
                    f"Best-value colleges in {st_name} by graduate earnings",
                    f"{st_name} colleges ranked by the share of their programs whose graduates "
                    f"out-earn a typical high-school graduate, from federal data.",
                    f"{BASE}/lists/best-value-colleges-{st.lower()}/",
                    f"Colleges in {st_name} whose graduates clear the bar most often",
                    "Ranked by the share of each school's programs whose graduates out-earn a "
                    "typical high-school graduate (the federal earnings-premium test).",
                    [
                        "College",
                        "Programs clearing the bar",
                        "Median earnings",
                        "Programs measured",
                    ],
                    cells,
                    f"Ranked on one stated metric, the share of a school's programs that clear the "
                    f"benchmark. Schools need at least {MIN_SCHOOL_PROGRAMS} programs with reported "
                    "earnings to appear. Note that specialised graduate institutions (medical and "
                    "health-science centres, for example) often rank at the top because their "
                    "programs are almost all high-earning; the 'programs measured' column and each "
                    "school's page give the context.",
                    f"best-value-colleges-{st.lower()}",
                ),
            )
        )
    return out


def render_index(entries) -> str:
    canonical = f"{BASE}/lists/"
    p = [
        head(
            "Rankings and lists from federal education data",
            "Highest and lowest paying majors, fastest debt payback, and the colleges in each "
            "state whose graduates most often out-earn a high-school graduate. Each list ranks on "
            "one stated metric from public federal data.",
            canonical,
        )
    ]
    p.append('  <main class="wrap pg">\n')
    p.append('    <nav class="crumbs">Lists</nav>\n')
    p.append("    <h1>Lists and rankings</h1>\n")
    p.append(
        '    <p class="idline">Every list here ranks on <b>one stated metric</b> from public '
        "federal data, with its denominator and minimum-sample rule printed on the page. No "
        "weighted score, no opinion index, no pay-to-play.</p>\n"
    )
    nat = [e for e in entries if not e[0].startswith("best-value-colleges-")]
    st = [e for e in entries if e[0].startswith("best-value-colleges-")]
    p.append('    <h2 class="sec">Majors and programs</h2>\n')
    p.append('    <ul class="schoollist">\n')
    for slug, h1, _ in nat:
        p.append(f'      <li><a href="/lists/{slug}/">{esc(h1)}</a></li>\n')
    p.append("    </ul>\n")
    p.append('    <h2 class="sec">Colleges by state</h2>\n')
    p.append('    <div class="statecols">\n')
    for slug, _, _ in st:
        code = slug.rsplit("-", 1)[-1].upper()
        p.append(f'      <a href="/lists/{slug}/">{esc(STATE_NAMES.get(code, code))}</a>\n')
    p.append("    </div>\n")
    p.append("  </main>\n")
    p.append(FOOTER)
    p.append(BEACON)
    p.append("</body>\n</html>\n")
    return "".join(p)


def main() -> None:
    con = duckdb.connect()
    _views(con)

    # Slug maps so list rows can link to the existing major and college pages.
    cip_slugs, used = {}, set()
    for (field,) in con.sql(
        "SELECT DISTINCT rtrim(cip_desc,'. ') FROM p WHERE cip_desc IS NOT NULL"
    ).fetchall():
        cand = slugify(field)
        if cand not in used:
            used.add(cand)
            cip_slugs[field] = cand

    # Reuse the college-page slug builder itself (not a copy), so list links can never 404.
    schools, _, _ = build_model(con)
    slugs_by_unitid = build_slugs(qualifying_schools(schools))

    entries = build_major_lists(con, cip_slugs) + build_state_lists(con, slugs_by_unitid)
    lists_dir = SITE / "lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    for slug, _, page_html in entries:
        d = lists_dir / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page_html)
    (lists_dir / "index.html").write_text(render_index(entries))
    print(f"lists: {len(entries):,} pages -> {lists_dir}")


if __name__ == "__main__":
    main()
