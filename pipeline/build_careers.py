"""Generate the Careers field-of-study data (what a major typically earns).

Aggregates the program-level Value Check table up to the national field level, one row
per 4-digit CIP x credential, and writes site/careers/data/fields.json. Each field carries
median earnings, the 25th-75th percentile spread across programs, how many programs and
schools report it, and the Value Check pass rate (share of programs whose graduates clear
the earnings-premium bar).

If a demand table (data/parquet/careers_demand.parquet, built from BLS by
pipeline.build_careers_demand) is present, each field is enriched with its occupation
outlook (projected growth and annual openings). Wages ship with or without it.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_careers
"""

from __future__ import annotations

import json

import duckdb

from pipeline.config import PARQUET_DIR, ROOT
from pipeline.program_unit import programs_sql

OUT_DIR = ROOT / "site" / "careers" / "data"
MIN_PROGRAMS = 5  # a field needs at least this many decided programs to be reported

# Standard 2-digit CIP series titles, for grouping majors into broad areas when browsing.
CIP_FAMILIES = {
    "01": "Agriculture & Natural Resources",
    "03": "Natural Resources & Conservation",
    "04": "Architecture",
    "05": "Area, Ethnic & Gender Studies",
    "09": "Communication & Journalism",
    "10": "Communications Technologies",
    "11": "Computer & Information Sciences",
    "12": "Personal & Culinary Services",
    "13": "Education",
    "14": "Engineering",
    "15": "Engineering Technologies",
    "16": "Foreign Languages & Linguistics",
    "19": "Family & Consumer Sciences",
    "22": "Legal Professions & Studies",
    "23": "English Language & Literature",
    "24": "Liberal Arts & Humanities",
    "25": "Library Science",
    "26": "Biological & Biomedical Sciences",
    "27": "Mathematics & Statistics",
    "28": "Military Science & Technologies",
    "29": "Military Technologies",
    "30": "Interdisciplinary Studies",
    "31": "Parks, Recreation & Fitness",
    "32": "Basic Skills",
    "33": "Citizenship Activities",
    "34": "Health-Related Knowledge",
    "35": "Interpersonal Skills",
    "36": "Leisure & Recreational Activities",
    "37": "Personal Awareness",
    "38": "Philosophy & Religious Studies",
    "39": "Theology & Religious Vocations",
    "40": "Physical Sciences",
    "41": "Science Technologies",
    "42": "Psychology",
    "43": "Homeland Security & Law Enforcement",
    "44": "Public Administration & Social Service",
    "45": "Social Sciences",
    "46": "Construction Trades",
    "47": "Mechanic & Repair Technologies",
    "48": "Precision Production",
    "49": "Transportation & Materials Moving",
    "50": "Visual & Performing Arts",
    "51": "Health Professions",
    "52": "Business & Management",
    "53": "High School / Secondary Diplomas",
    "54": "History",
    "60": "Residency Programs",
}

CRED_SHORT = {
    "Bachelor's Degree": "Bachelor's",
    "Master's Degree": "Master's",
    "Doctoral Degree": "Doctoral",
    "Associate's Degree": "Associate's",
    "First Professional Degree": "First prof.",
    "Undergraduate Certificate or Diploma": "Undergrad cert",
    "Graduate/Professional Certificate": "Grad cert",
    "Post-baccalaureate Certificate": "Post-bacc cert",
}


def _round(x):
    return None if x is None else int(round(x))


def build_fields(con) -> list[dict]:
    """Aggregate the Value Check table into per-field (CIP x credential) rows.

    Shared by the JSON builder (this module) and the static /majors/ page builder
    (build_majors_pages), so every major page shows the same numbers as the app.
    """
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    rows = con.execute(
        f"""
        SELECT
            cip_code,
            any_value(cip_desc)         AS cip_desc,
            credential_level,
            any_value(credential_desc)  AS credential_desc,
            count(*) FILTER (WHERE value_flag != 'insufficient_data')          AS programs,
            count(DISTINCT unitid)                                             AS schools,
            median(earnings)                                                   AS med,
            quantile_cont(earnings, 0.25)                                      AS p25,
            quantile_cont(earnings, 0.75)                                      AS p75,
            count(*) FILTER (WHERE value_flag = 'passes_earnings_premium')     AS n_pass
        FROM {programs_sql(vc)}
        WHERE regexp_matches(unitid, '^[0-9]+$') AND earnings IS NOT NULL
              AND value_flag != 'insufficient_data'
        GROUP BY cip_code, credential_level
        HAVING programs >= {MIN_PROGRAMS}
        ORDER BY cip_desc, credential_level
        """
    ).fetchall()

    fields = []
    for cip, cip_desc, cred, cred_desc, programs, schools, med, p25, p75, n_pass in rows:
        name = (cip_desc or "").rstrip(". ")
        cip2 = (cip or "")[:2]
        fields.append(
            {
                "cip": cip,
                "cip2": cip2,
                "family": CIP_FAMILIES.get(cip2, "Other"),
                "name": name,
                "cred": cred,
                "credential": cred_desc,
                "cred_short": CRED_SHORT.get(cred_desc, cred_desc),
                "med": _round(med),
                "p25": _round(p25),
                "p75": _round(p75),
                "programs": programs,
                "schools": schools,
                "pass_pct": round(100 * n_pass / programs) if programs else None,
            }
        )

    # Optional BLS demand layer (occupation outlook), merged by 4-digit CIP.
    demand_path = PARQUET_DIR / "careers_demand.parquet"
    n_demand = 0
    if demand_path.exists():
        demand = {
            r[0]: r[1]
            for r in con.execute(
                f"SELECT cip_code, demand_json FROM read_parquet('{demand_path}')"
            ).fetchall()
        }
        for f in fields:
            d = demand.get(f["cip"])
            if d:
                f["demand"] = json.loads(d)
                n_demand += 1

    return fields


STATIC_ROWS = 25  # one page of the reveal, matching the PAGE constant in the page's own script
CORE_START = "<!-- CAREERS_CORE_START -->"
CORE_END = "<!-- CAREERS_CORE_END -->"
PAGE_HTML = ROOT / "site" / "careers" / "index.html"


def _esc(s) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _money(n) -> str:
    if n is None:
        return "n/a"
    v = int(round(n))
    return f"-${abs(v):,}" if v < 0 else f"${v:,}"


def static_core(fields: list[dict]) -> str:
    """The first page of rows, server-rendered, so Careers carries data without JavaScript.

    It was the one data page that degraded to nothing: the table was built entirely in the browser
    from a 785 KB JSON, so with scripting off a reader got a paragraph pointing at the methodology
    page. The profile pages have shipped a static core since Stage 4.1 and this is the same contract,
    at the same page size, 25 rows.

    Two deliberate choices.

    The order is the page's own default, earnings descending, so the static rows ARE the opening view
    rather than a different set that the script then replaces. A visitor with JavaScript sees the same
    25 rows they would have seen anyway, which is what makes this progressive enhancement rather than
    two implementations of one table.

    The links go to `/majors/<slug>/`, not to the page's own `?field=` route. That route is itself
    rendered in the browser, so linking a no-JavaScript reader into it would hand them a second empty
    page. Every one of the 292 CIPs here has a real major page, checked rather than assumed.
    """
    from pipeline.build_majors_pages import major_slugs

    slugs = major_slugs(fields)
    rows = sorted(fields, key=lambda f: (-(f["med"] or -1), f["name"], f["cred"]))[:STATIC_ROWS]
    out = []
    for f in rows:
        slug = slugs.get(f["cip"])
        name = _esc(f["name"])
        link = f'<a href="/majors/{slug}/">{name}</a>' if slug else name
        # Unknown reads "insufficient data", never "n/a": the same rule as every other page, and the
        # phrase the methodology defines. "n/a" says "does not apply", which is a different claim.
        pass_txt = "insufficient data" if f["pass_pct"] is None else f"{f['pass_pct']}%"
        band = (
            f"{_money(f['p25'])} to {_money(f['p75'])}"
            if f["p25"] is not None and f["p75"] is not None
            else "insufficient data"
        )
        out.append(
            f'          <tr data-cip="{_esc(f["cip"])}" data-cred="{_esc(f["cred"])}">'
            f'<td class="mname">{link}<div class="fam">{_esc(f["family"])}</div></td>'
            f'<td data-label="Degree">{_esc(f["cred_short"])}</td>'
            f'<td class="num" data-label="Median earnings">{_money(f["med"])}</td>'
            f'<td data-label="Typical range">{band}</td>'
            f'<td class="num" data-label="Clear the bar">{pass_txt}</td>'
            f'<td class="num" data-label="Schools">{(f["schools"] or 0):,}</td></tr>'
        )
    body = "\n".join(out)
    return (
        f"{CORE_START}\n"
        '        <div class="table-wrap" tabindex="0" role="region" aria-label="Majors and earnings">\n'
        '        <table class="cr-table">\n'
        "          <caption>The highest-earning major and degree combinations. "
        f"Showing {STATIC_ROWS} of {len(fields):,}; the full list needs JavaScript, and every major "
        "here has its own page.</caption>\n"
        '          <thead><tr><th>Major</th><th>Degree</th><th class="num">Median earnings</th>'
        '<th>Typical range</th><th class="num">Clear the bar</th><th class="num">Schools</th>'
        "</tr></thead>\n"
        f"          <tbody>\n{body}\n          </tbody>\n"
        "        </table></div>\n"
        f"        {CORE_END}"
    )


def inject_core(fields: list[dict]) -> None:
    """Write the static core between the markers in the shipped page.

    Refuses a set too small to fill the core. This is not defensiveness for its own sake: putting the
    injection in main() meant `pytest` began rewriting this tracked file, because tests/test_careers
    calls main() against a synthetic parquet and redirects OUT_DIR but not this page. One run left the
    shipped page reading "Showing 25 of 1" with a single row. A generator that silently replaces a
    6,127-row release artefact with a fixture's output is worse than one that stops, so it stops. The
    test now redirects PAGE_HTML as well; this guard is what makes the next such caller fail loudly.
    """
    if len(fields) < STATIC_ROWS:
        raise SystemExit(
            f"refusing to write the careers core from {len(fields)} fields: it cannot fill "
            f"{STATIC_ROWS} rows, and overwriting the shipped page with a stub would be worse than "
            "failing. Point PAGE_HTML at a scratch file if this is a test."
        )
    html = PAGE_HTML.read_text()
    if CORE_START not in html or CORE_END not in html:
        raise SystemExit(
            f"{PAGE_HTML} is missing the {CORE_START} / {CORE_END} markers, so the "
            "no-JavaScript core cannot be written. Restore them rather than skipping: without the "
            "core this page carries no data at all with scripting off."
        )
    pre, rest = html.split(CORE_START, 1)
    _, post = rest.split(CORE_END, 1)
    PAGE_HTML.write_text(pre + static_core(fields) + post)


def main() -> None:
    con = duckdb.connect()
    fields = build_fields(con)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fields.json").write_text(
        json.dumps({"generated": True, "fields": fields}, separators=(",", ":"))
    )
    inject_core(fields)
    n_demand = sum(1 for f in fields if "demand" in f)
    print(f"careers fields: {len(fields):,}  |  with demand: {n_demand:,}")
    print(f"wrote -> {OUT_DIR / 'fields.json'}")
    print(f"wrote -> {PAGE_HTML} ({STATIC_ROWS} static rows)")


if __name__ == "__main__":
    main()
