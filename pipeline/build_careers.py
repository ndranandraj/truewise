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


def main() -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con = duckdb.connect()
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
        FROM read_parquet('{vc}')
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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fields.json").write_text(
        json.dumps({"generated": True, "fields": fields}, separators=(",", ":"))
    )
    print(f"careers fields: {len(fields):,}  |  with demand: {n_demand:,}")
    print(f"wrote -> {OUT_DIR / 'fields.json'}")


if __name__ == "__main__":
    main()
