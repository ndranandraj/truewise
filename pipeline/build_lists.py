"""Generate ranked list pages: /lists/<slug>/ plus one list of colleges per state.

Every list ranks on ONE stated metric, with its denominator and minimum-sample rule printed on the
page. No weighted opinion index, no composite score. Each row links to the underlying college or
major page.

The state lists rank colleges by the share of their programs whose graduates earned more than a
typical high-school graduate. Price is not in that measure, so the pages no longer call it "best
value" (November 2026). Their addresses still say best-value-colleges-<state>: an address is a
contract with every link to it, and the site has no redirects.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_lists
"""

from __future__ import annotations

import csv
import html
import io
import re
from typing import NamedTuple

import duckdb

from pipeline.build_college_pages import (
    BASE,
    BEACON,
    FOOTER,
    build_slugs,
    esc,
    head,
    known_state,
    money,
    qualifying_schools,
    slugify,
    state_label,
)
from pipeline.build_site import build_model
from pipeline.config import PARQUET_DIR, ROOT
from pipeline.og_images import card as render_card
from pipeline.program_unit import programs_sql

SITE = ROOT / "site"
MIN_PROGRAMS = 10  # a major needs this many reported programs to be ranked
MIN_SCHOOL_PROGRAMS = 10  # a school needs this many decided programs to be ranked
TOP_N = 25


def _ranked(metric: str) -> str:
    """End a field list's query: order by its metric, then name, and cut without splitting a tie.

    With no unique final key, DuckDB leaves equal rows in whichever order its threads finish, so the
    order changed between builds with no change in the data. A tie at the cut changed which fields
    appeared at all (three fields at 20 programs for the debt list's last two places). Every field
    tied at the cut is kept, so a list can run past TOP_N rather than drop one for how its name sorts.
    """
    return (
        f"QUALIFY rank() OVER (ORDER BY {metric}) <= {TOP_N} ORDER BY {metric}, lower(field), field"
    )


def _views(con) -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con.execute(
        f"""CREATE OR REPLACE VIEW p AS SELECT * FROM read_parquet('{vc}')
            WHERE regexp_matches(unitid, '^[0-9]+$')"""
    )
    # Field-level lists count each program once (pipeline/program_unit.py); school-level lists
    # (the view below) stay per campus, because a campus page is what they link to.
    con.execute(
        f"""CREATE OR REPLACE VIEW pu AS SELECT * FROM {programs_sql(vc)}
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


def _csv_text(headers, rows, ranks=None) -> str:
    """Build the CSV from the same rows the table renders, so the two cannot disagree.

    ranks is the rank printed beside each row where rows can share one; without it rows are
    numbered in order."""
    ranks = _ranks_for(rows, ranks)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["rank", *[_strip_tags(h) for h in headers]])
    for rank, cells in zip(ranks, rows, strict=True):
        w.writerow([rank, *[_strip_tags(c) for c in cells]])
    return buf.getvalue()


def _ranks_for(rows, ranks) -> list:
    """One rank per row. A list that is a different length would print ranks against the wrong
    rows, so that stops the build."""
    if ranks is None:
        return list(range(1, len(rows) + 1))
    ranks = list(ranks)
    if len(ranks) != len(rows):
        raise ValueError(f"{len(ranks)} ranks for {len(rows)} rows")
    return ranks


CSV_DIR = "/data/lists"


def csv_filename(slug: str) -> str:
    return f"truewise-{slug}-scorecard-2026-06-10.csv"


def _download_block(slug) -> str:
    """A link to a real file.

    This used to inline the whole CSV as JSON and build a Blob on click. That worked, but no
    request ever reached the server, so downloads were unmeasurable without adding an event
    endpoint, and the file had no address anyone could cite or link to. Writing the CSV at build
    time fixes both with LESS machinery: the download becomes an ordinary request that Cloudflare's
    existing logs already record, no new collection of any kind, and every list gains a stable URL
    for the /data/ page to point at.

    It also takes the table's own bytes back out of the page, which were duplicated in full.
    """
    fname = csv_filename(slug)
    return (
        f'    <p class="dl"><a class="btn btn--secondary" href="{CSV_DIR}/{fname}" download>'
        "Download this table (CSV)</a>"
        '<span class="dl-note"> Free to reuse with attribution (CC BY 4.0).</span></p>\n'
    )


def write_csv(slug, headers, rows, ranks=None) -> int:
    """Write the list's CSV beside the site and return its byte length."""
    out = SITE / CSV_DIR.lstrip("/") / csv_filename(slug)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = _csv_text(headers, rows, ranks)
    out.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _page(
    title,
    desc,
    canonical,
    h1,
    lede,
    headers,
    rows,
    note,
    slug,
    *,
    ranks=None,
    rank_head="#",
    above="",
    card_headline=None,
    card_sub=None,
    csv_table=None,
) -> str:
    """One list page, its share card and its CSV.

    ranks: the rank printed for each row, where rows can share one (default 1, 2, 3 in row order).
    above: HTML between the introduction and the table, for what a reader needs to read the order.
    note: one paragraph of small print, or several.
    card_headline: the share card's heading, where the page heading is too long to fit on it.
    card_sub: the share card's line, where "#1: <first row>" would name a row that is first only
        by a tie-break. One line, or several from fullest to shortest: the first that fits the
        card is used, and the build stops if none does, because a cut caption can lose the words
        that say what a figure measures.
    csv_table: (headers, rows) for the download, where it gives a table cell as separate columns.
    """
    ranks = _ranks_for(rows, ranks)
    # A share card whose hook is the #1 entry, so a posted ranking is not a generic card.
    top = _strip_tags(rows[0][0]) if rows else ""
    if card_sub is None:
        render_card(
            SITE / "og" / "lists" / f"{slug}.png",
            "Ranked list · US education data",
            card_headline or h1,
            big=None,
            sub=(f"#1: {top}." if top else _strip_tags(lede)),
        )
    else:
        for line in [card_sub] if isinstance(card_sub, str) else card_sub:
            cut = render_card(
                SITE / "og" / "lists" / f"{slug}.png",
                "Ranked list · US education data",
                card_headline or h1,
                big=None,
                sub=line,
            )
            if not cut:
                break
        else:
            raise SystemExit(f"lists: no share-card line for {slug} fits the card")
    p = [head(title, desc, canonical, og_image=f"/og/lists/{slug}.png")]
    p.append('  <main class="wrap pg">\n')
    p.append(f'    <nav class="crumbs"><a href="/lists/">Lists</a> &rsaquo; {esc(h1)}</nav>\n')
    p.append(f"    <h1>{esc(h1)}</h1>\n")
    p.append(f'    <p class="idline">{lede}</p>\n')
    p.append(above)
    p.append(
        '    <div class="tscroll" tabindex="0" role="region" aria-label="Ranking"><table class="t"><thead><tr>'
        f'<th class="num">{esc(rank_head)}</th>'
    )
    num_attr = " class='num'"
    for i, hd in enumerate(headers):
        p.append("<th" + (num_attr if i else "") + ">" + esc(hd) + "</th>")
    p.append("</tr></thead><tbody>\n")
    for rank, cells in zip(ranks, rows, strict=True):
        p.append(f"      <tr><td class='num'>{rank}</td>")
        for j, c in enumerate(cells):
            p.append("<td" + (num_attr if j else "") + ">" + str(c) + "</td>")
        p.append("</tr>\n")
    p.append("    </tbody></table></div>\n")
    csv_headers, csv_rows = csv_table or (headers, rows)
    write_csv(slug, csv_headers, csv_rows, ranks)
    p.append(_download_block(slug))
    for para in [note] if isinstance(note, str) else note:
        p.append(f'    <p class="src">{para}</p>\n')
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
        FROM pu WHERE credential_level='3' AND value_flag != 'insufficient_data'
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} {_ranked("med DESC")}""")
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
        FROM pu WHERE credential_level='3' AND value_flag != 'insufficient_data'
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} {_ranked("med ASC")}""")
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
        FROM pu WHERE credential_level='3' AND debt_payback_years IS NOT NULL
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} ORDER BY pb ASC, field LIMIT {TOP_N}""")
    out.append(
        (
            "fastest-debt-payback-majors",
            "Bachelor's majors with the lowest debt relative to earnings gain",
            _page(
                "Bachelor's majors with the lowest debt relative to graduates' earnings gain",
                "Bachelor's majors ranked by median federal debt divided by how much more graduates "
                "earn per year than a typical high-school graduate. Federal data.",
                f"{BASE}/lists/fastest-debt-payback-majors/",
                "Bachelor's majors with the lowest debt relative to earnings gain",
                "Median federal debt divided by the yearly earnings gain over a typical high-school "
                "graduate, lowest first. Bachelor's degrees only.",
                ["Major", "Debt as years of gain", "Programs"],
                [(_major_link(f, cip_slugs), f"{pb:g} yrs", f"{n:,}") for f, pb, n in r],
                "Debt as years of gain is median federal debt divided by the yearly earnings gain "
                "over a typical high-school graduate. It is a plain ratio, not how long repayment "
                "takes: it ignores interest, taxes, living costs and time to degree, and it is not "
                "the federal debt-to-earnings rate. Each program is counted once.",
                "fastest-debt-payback-majors",
            ),
        )
    )

    # 4. Fields where debt most often does not pay back.
    r = rows_for(f"""
        SELECT rtrim(cip_desc,'. ') AS field, count(*) AS n,
               round(median(debt_median)) AS debt, round(median(earnings)) AS earn
        FROM pu WHERE value_flag='fails_earnings_premium' AND debt_median IS NOT NULL
        GROUP BY field HAVING count(*) >= {MIN_PROGRAMS} {_ranked("n DESC")}""")
    out.append(
        (
            "programs-where-debt-does-not-pay-back",
            "Fields with the most programs below the high-school line that report debt",
            _page(
                "Programs below the high-school earnings line that report debt, by field",
                "Fields with the most programs whose graduates' median earnings fall below a typical "
                "high-school graduate's, among programs that report median federal debt. Federal data.",
                f"{BASE}/lists/programs-where-debt-does-not-pay-back/",
                "Programs below the high-school line that report debt, by field",
                "Fields with the most programs whose graduates both fall short of a typical "
                "high-school graduate's earnings and carry federal debt.",
                ["Field of study", "Programs", "Median debt", "Median earnings"],
                [(_major_link(f, cip_slugs), f"{n:,}", money(d), money(e)) for f, n, d, e in r],
                "Counted across all credential levels: programs flagged as falling short of the "
                "state high-school-graduate earnings benchmark that also report median debt. "
                f"Fields with the same count are listed alphabetically. A tie at the cut-off is "
                f"kept, so this list can run past {TOP_N} rows. A program appearing here is a "
                "signal to ask questions, not a verdict on any student.",
                "programs-where-debt-does-not-pay-back",
            ),
        )
    )
    return out


class Ranked(NamedTuple):
    """One college on a state list."""

    unitid: str
    name: str
    compared: int  # programs with published earnings and a state high-school line
    above: int  # of those, the programs whose graduates earned more than that line
    median: float | None  # the middle of the college's program medians
    rank: int  # by the share above / compared; colleges with the same share have the same rank
    eligible: int  # colleges in the state with enough programs to be ranked


def state_ranking(con, st: str) -> list[Ranked]:
    """A state's colleges ranked by the share of their programs above the high-school line.

    The rank is on the exact share. Until November 2026 the order was on the percentage rounded to
    a whole number, so 13 of 14 and 14 of 15 (both "93%") counted as a tie and the higher earner
    went first, ahead of the college with the higher share. Colleges with the same share get
    the same rank, and the cut keeps every college tied at it, so a list can run past TOP_N rather
    than drop a college for its earnings or its name. Median earnings, then name, then federal ID
    only settle the order of rows within one rank.
    """
    rows = con.execute(
        f"""
        WITH e AS (
            SELECT unitid, nm, n_dec, n_pass, n_pass::DOUBLE / n_dec AS share,
                   round(med_earn) AS med
            FROM sch WHERE st = ? AND n_dec >= {MIN_SCHOOL_PROGRAMS}
        )
        SELECT unitid, nm, n_dec, n_pass, med, rank() OVER (ORDER BY share DESC) AS rk,
               count(*) OVER () AS eligible
        FROM e QUALIFY rk <= {TOP_N}
        ORDER BY share DESC, med DESC, lower(nm), unitid
        """,
        [st],
    ).fetchall()
    return [Ranked(*r) for r in rows]


def share_text(above: int, compared: int) -> str:
    """The share as a percentage, with one decimal where it has one ("96.3%", "100%").

    A share short of every program is never printed as 100%, and one above none never as 0%: the
    count beside it would say otherwise."""
    pct = 100.0 * above / compared
    if above < compared:
        pct = min(pct, 99.9)
    if above > 0:
        pct = max(pct, 0.1)
    return f"{pct:.1f}".rstrip("0").rstrip(".") + "%"


_TIE_ORDER = "Colleges with the same share are listed by median earnings, highest first"


def tie_sentence(rows: list[Ranked]) -> str:
    """What a reader needs to read the order: how many colleges share first place, and what orders
    colleges that share a rank. Printed above the table, never in the small print."""
    top = [r for r in rows if r.rank == 1]
    share = share_text(top[0].above, top[0].compared)
    if len(top) == len(rows) and len(rows) > 1:
        return (
            f"<b>All {len(rows)} colleges shown have the same share, {share}.</b> The share cannot "
            f"order them. {_TIE_ORDER}, and that is the only order on this page."
        )
    if len(top) > 1:
        return (
            f"<b>{len(top)} colleges share first place at {share}.</b> {_TIE_ORDER}; they keep "
            "the same rank."
        )
    return f"{_TIE_ORDER}; they keep the same rank."


CARD_MEASURE = "By share of programs whose graduates earned more than a high-school graduate."


def card_lines(rows: list[Ranked]) -> list[str]:
    """The share card's caption, fullest first. The measure always comes first, because a share
    quoted without it means nothing. A college is named only when one college is first on the
    measure, and only if its name fits."""
    top = [r for r in rows if r.rank == 1]
    if len(top) == 1:
        return [f"{CARD_MEASURE} #1: {top[0].name}.", f"{CARD_MEASURE} One college is first."]
    share = share_text(top[0].above, top[0].compared)
    return [f"{CARD_MEASURE} {len(top)} colleges share first place at {share}."]


DESC_MAX = 155  # a longer description is cut in a search result


def state_description(st_name: str) -> str:
    """The search description, in the fullest wording that fits."""
    for programs in ("their programs", "programs"):
        text = (
            f"{st_name} colleges ranked by the share of {programs} whose graduates earned more "
            "than a typical high-school graduate. Ties are shown as ties."
        )
        if len(text) <= DESC_MAX:
            return text
    raise ValueError(f"no description for {st_name} fits {DESC_MAX} characters")


STATE_NOTES = (
    "Every degree level is counted, graduate programs included, against the high-school line. "
    "That is Truewise&rsquo;s comparison and not the federal earnings test, which compares "
    "graduate programs with bachelor&rsquo;s degree holders. "
    '<a href="/earnings-test/">What the test is</a>. Colleges that teach mostly graduate health '
    "programs are often at the top for that reason.",
    "Median earnings is the middle of the college&rsquo;s program medians, not the earnings of "
    "its typical graduate. Colleges with the same share and the same median earnings are listed "
    "by name.",
)


def build_state_lists(con, slugs_by_unitid) -> list[tuple[str, str, str]]:
    """One list per state: its colleges by how often graduates out-earn a high-school graduate."""
    out = []
    states = [
        r[0]
        for r in con.sql(
            f"""SELECT st FROM sch WHERE n_dec >= {MIN_SCHOOL_PROGRAMS} AND st IS NOT NULL
                GROUP BY st HAVING count(*) >= 5 ORDER BY st"""
        ).fetchall()
    ]
    for st in states:
        # Never rank a "state" the data did not report; the label would be a fiction.
        if not known_state(st):
            continue
        rows = state_ranking(con, st)
        st_name = state_label(st)
        cells, csv_cells = [], []
        for r in rows:
            slug = slugs_by_unitid.get(r.unitid)
            link = f'<a href="/college/{slug}/">{esc(r.name)}</a>' if slug else esc(r.name)
            share = share_text(r.above, r.compared)
            cells.append(
                (
                    link,
                    f"{r.above:,} of {r.compared:,} <span class='ln-pct'>({share})</span>",
                    money(r.median),
                )
            )
            csv_cells.append((link, f"{r.above:,}", f"{r.compared:,}", share, money(r.median)))
        eligible = rows[0].eligible
        past = (
            f" {len(rows)} are shown, not {TOP_N}, because the cut would have split colleges "
            "with the same share."
            if len(rows) > TOP_N
            else ""
        )
        h1 = f"Colleges in {st_name} whose graduates most often out-earn a high-school graduate"
        out.append(
            (
                f"best-value-colleges-{st.lower()}",
                h1,
                _page(
                    f"Colleges in {st_name}: how often graduates out-earn a high-school graduate",
                    state_description(st_name),
                    f"{BASE}/lists/best-value-colleges-{st.lower()}/",
                    h1,
                    "Ranked by one measure: the share of each college&rsquo;s programs whose "
                    f"graduates earned more than a typical {esc(st_name)} high-school graduate. "
                    f"{eligible:,} colleges in {esc(st_name)} have at least "
                    f"{MIN_SCHOOL_PROGRAMS} programs that can be compared.{past}",
                    ["College", "Programs above the line", "Median earnings"],
                    cells,
                    STATE_NOTES,
                    f"best-value-colleges-{st.lower()}",
                    ranks=[r.rank for r in rows],
                    rank_head="Rank",
                    above=f'    <p class="ln-tie">{tie_sentence(rows)}</p>\n',
                    card_headline=f"Colleges in {st_name}",
                    card_sub=card_lines(rows),
                    csv_table=(
                        [
                            "College",
                            "Programs above the line",
                            "Programs compared",
                            "Share",
                            "Median earnings",
                        ],
                        csv_cells,
                    ),
                ),
            )
        )
    return out


def render_index(entries) -> str:
    canonical = f"{BASE}/lists/"
    p = [
        head(
            "Rankings and lists from federal education data",
            "Highest and lowest paying majors, debt compared with earnings gain, and the colleges in each "
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
        p.append(f'      <a href="/lists/{slug}/">{esc(state_label(code))}</a>\n')
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
        "SELECT DISTINCT rtrim(cip_desc,'. ') FROM p WHERE cip_desc IS NOT NULL ORDER BY 1"
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
