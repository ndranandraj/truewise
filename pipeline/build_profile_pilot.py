"""Stage 4.1 canonical-profile pilot.

Builds a representative sample of the future `/college/<slug>/` profile using the DELIVERY MODEL from
decision 0.1: static core HTML (identity, verdict, coverage, and the first N programs as a real,
crawlable table) plus a per-school tail JSON for the remaining programs, loaded on demand. The point
is to MEASURE page weight on the hard cases and validate the ~60-program static threshold BEFORE
generating all ~4,949 profiles or touching production.

Output goes to pilot/ (git-ignored, never deployed). This does not modify the live build.

Usage:
    python -m pipeline.build_profile_pilot          # build the 4 reps + print measurements
    python -m pipeline.build_profile_pilot --threshold 60
"""

from __future__ import annotations

import argparse
import gzip
import json

import duckdb

from pipeline.cip_names import plain_name, tidy_official
from pipeline.config import ROOT

PARQUET = ROOT / "published" / "value_check.parquet"
SITE = ROOT / "site"
OUT = ROOT / "pilot"

# The four representatives, chosen from the data to span the axes that stress the delivery model.
REPS = {
    "small": "461111",  # 3 programs
    "largest": "214777",  # 489 programs (Penn State main)
    "mostly-suppressed": "116439",  # 107 programs, 106 insufficient
    "long-name": "158325",  # a very long institution name (wrapping)
}

# Raised from 60 to 150 after the pilot: gzip makes transfer a non-issue (the worst 489-program page
# is 12.4 KB gzipped fully static), so the binding constraint is DOM size, not bytes. 150 keeps 95%
# of schools fully static and crawlable (p95 = 150 programs) and only sends the ~4.9% giants to
# progressive loading, purely to cap their DOM. See pilot report.
DEFAULT_THRESHOLD = 150


def _slug(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _esc(s) -> str:
    """HTML-escape any text inserted into the page. School and program names contain ampersands (and
    the full data will contain <, >, quotes), which would otherwise produce invalid markup across
    ~4,949 pages."""
    import html as _html

    return _html.escape(str(s if s is not None else ""), quote=True)


def _island_json(obj) -> str:
    """Serialize the JSON data island so embedded text cannot terminate the <script> element. Escaping
    every '<' as \\u003c is valid JSON and neutralises any '</script>' in the data by construction."""
    return json.dumps(obj, separators=(",", ":")).replace("<", "\\u003c")


def _money(v):
    return None if v is None else "$" + format(round(v), ",")


def _rows_for(con, unitid: str) -> tuple[dict, list[dict]]:
    df = con.sql(
        f"""
        SELECT any_value(inst_name) AS name, any_value(state) AS state,
               any_value(control) AS control
        FROM '{PARQUET}' WHERE unitid = '{unitid}'
        """
    ).df()
    meta = {
        "unitid": unitid,
        "name": df.iloc[0]["name"],
        "state": df.iloc[0]["state"],
        "control": df.iloc[0]["control"],
    }
    prog = con.sql(
        f"""
        SELECT cip_code, cip_desc, credential_desc, credential_level, earnings,
               earnings_premium_state, earnings_threshold_state, debt_median, debt_payback_years,
               completers_count, value_flag, earnings_horizon
        FROM '{PARQUET}' WHERE unitid = '{unitid}'
        -- Selection policy for the static tranche: ASSESSED programs (a real earnings verdict) first,
        -- then by completers within each group. A program with a verdict is the valuable, crawlable
        -- content; an insufficient-data row is nearly worthless to a searcher, so a decided program
        -- outranks a larger insufficient one. This is deliberately NOT "the 150 largest by
        -- completers" (an earlier report claim); it is "all assessed, then the largest of the rest".
        -- cip_code is the final, deterministic tie-breaker so the static/tail split is stable across
        -- builds (equal-completer programs would otherwise order arbitrarily and churn the URLs/tail).
        ORDER BY (value_flag IN ('passes_earnings_premium','fails_earnings_premium')) DESC,
                 completers_count DESC NULLS LAST, cip_code, credential_desc, earnings
        """
    ).df()
    # One row-construction path: _rows_for now calls _row_from, so the pilot and full-build tranches
    # carry an identical shape (including the earnings-window horizon). Divergence here is what let the
    # mixed-window label ship on one path and not the other, so the shared contract is now real.
    rows = [_row_from(r) for _, r in prog.iterrows()]
    return meta, rows


_MAJOR_SLUGS: dict[str, str] | None = None


def major_slug_for(cip_code) -> str | None:
    """The major page for a programme, joined on 4-digit CIP.

    The CIP is the exact relationship: a major page IS a 4-digit CIP. Matching on the programme
    name would be approximate, and the contract says exact relationships only, so a field with no
    major page (137 of 429 fall below the ranking threshold) simply gets no link rather than a
    guessed one.
    """
    global _MAJOR_SLUGS
    if _MAJOR_SLUGS is None:
        # The map is derived from value_check.parquet, which is data rather than source and is
        # gitignored. CI runs pytest WITHOUT building it, so this has to answer "no link" there
        # rather than raise: a row builder that needs the warehouse to construct a row would fail
        # every test that touches one. The condition is the parquet itself, not a bare except, so
        # a real build with the data present still surfaces any error in building the map.
        from pipeline.config import PARQUET_DIR

        if not (PARQUET_DIR / "value_check.parquet").exists():
            _MAJOR_SLUGS = {}
        else:
            import duckdb

            from pipeline.build_majors_pages import build_fields, major_slugs

            _MAJOR_SLUGS = major_slugs(build_fields(duckdb.connect()))
    return _MAJOR_SLUGS.get(str(cip_code)[:4])


def _row_from(r) -> dict:
    """Map one parquet program record to the canonical row shape (shared by _rows_for and all_profiles)."""
    decided = r["value_flag"] in ("passes_earnings_premium", "fails_earnings_premium")
    # ED published earnings but there is no state line to compare them with (the school is not in
    # ED's current institution file: mostly closed or merged schools and territories). The earnings
    # are real and are shown; only the verdict is withheld. They used to read "insufficient data".
    nobench = (
        not decided
        and _num(r.get("earnings")) is not None
        and _num(r.get("earnings_threshold_state")) is None
    )
    shown = decided or nobench
    return {
        "program": plain_name(str(r["cip_code"]), r["cip_desc"]) or tidy_official(r["cip_desc"]),
        "credential": r["credential_desc"],
        "earnings": _num(r["earnings"]) if shown else None,
        "premium": None if not decided else _num(r["earnings_premium_state"]),
        "verdict": "pass"
        if r["value_flag"] == "passes_earnings_premium"
        else "fail"
        if r["value_flag"] == "fails_earnings_premium"
        else "nobench"
        if nobench
        else "insufficient",
        # Graduate credentials are compared with the high-school line here, which is not the federal
        # graduate test (the 2026 rule uses a bachelor's-holder line), so their verdict is worded
        # as a comparison, not as clearing the federal bar.
        "grad": str(r.get("credential_level") or "") in GRAD_LEVELS,
        # Horizon only for a DISPLAYED value. Insufficient rows hide their earnings, so their
        # horizon must stay None or they would trip the 1-year label/notice for a figure never shown.
        "horizon": r["earnings_horizon"] if shown else None,
        "debt": _num(r["debt_median"]),
        "payback": _num(r["debt_payback_years"]),
        "completers": _num(r["completers_count"]),
        # Carried in the row shape rather than resolved per renderer, so the static core and the
        # progressive tail cannot link to different places for the same programme.
        "major": major_slug_for(r["cip_code"]),
    }


def all_profiles(con, parquet=None) -> dict[str, tuple[dict, list[dict]]]:
    """One-pass {unitid: (meta, rows)} for every school, so the cutover build does not run a query per
    school. Same row shape and assessed-first ordering as _rows_for. Sources programs from the parquet
    (not the value-check shards, which strip insufficient programs to name+credential and drop
    completers), so suppressed rows keep their real completers count.

    The parquet path defaults to build_site.PARQUET_DIR (resolved at call time, not import) so it tracks
    the same source of truth as build_model and honours a test's monkeypatch of PARQUET_DIR."""
    if parquet is None:
        from pipeline import build_site as _bs

        parquet = _bs.PARQUET_DIR / "value_check.parquet"
    have = {r[0] for r in con.sql(f"DESCRIBE SELECT * FROM '{parquet}'").fetchall()}

    def col(name: str) -> str:
        # Hand-made test fixtures omit some columns; supply NULL so the row shape is unchanged.
        return name if name in have else f"NULL AS {name}"

    grp = "coalesce(opeid6, unitid)" if "opeid6" in have else "unitid"
    lvl = "credential_level" if "credential_level" in have else "NULL"
    df = con.sql(
        f"""
        SELECT unitid, inst_name, state, control, cip_code, cip_desc, credential_desc,
               {col("credential_level")}, earnings, earnings_premium_state,
               {col("earnings_threshold_state")},
               debt_median, debt_payback_years, completers_count, value_flag, earnings_horizon,
               {col("opeid6")},
               count(*) OVER (PARTITION BY {grp}, cip_code, {lvl}) AS n_campuses
        FROM '{parquet}'
        WHERE TRY_CAST(unitid AS BIGINT) IS NOT NULL
        ORDER BY unitid,
                 (value_flag IN ('passes_earnings_premium','fails_earnings_premium')) DESC,
                 completers_count DESC NULLS LAST, cip_code, credential_desc, earnings
        """
    ).df()
    out: dict[str, tuple[dict, list[dict]]] = {}
    for r in df.itertuples(index=False):
        u = str(r.unitid)
        if u not in out:
            out[u] = (
                {
                    "unitid": u,
                    "name": r.inst_name,
                    "state": r.state,
                    "control": r.control,
                    "opeid6": r.opeid6,
                    # Programs whose figures ED reports for several campuses under one OPEID.
                    "shared": 0,
                },
                [],
            )
        if r.n_campuses and r.n_campuses > 1:
            out[u][0]["shared"] += 1
        out[u][1].append(
            _row_from(
                {
                    "value_flag": r.value_flag,
                    "cip_code": r.cip_code,
                    "cip_desc": r.cip_desc,
                    "credential_desc": r.credential_desc,
                    "credential_level": r.credential_level,
                    "earnings": r.earnings,
                    "earnings_premium_state": r.earnings_premium_state,
                    "earnings_threshold_state": r.earnings_threshold_state,
                    "debt_median": r.debt_median,
                    "debt_payback_years": r.debt_payback_years,
                    "completers_count": r.completers_count,
                    "earnings_horizon": r.earnings_horizon,
                }
            )
        )
    return out


def _num(v):
    import math

    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else (int(f) if f == int(f) else round(f, 1))
    except (TypeError, ValueError):
        return None


def _program_cell(r: dict) -> str:
    """The programme name, linked to its major page when one exists.

    A real anchor, crawlable and keyboard-focusable, and rendered identically here and in the JS
    component so enhancement does not change where a row points. Before this the median college
    page took two impressions in 28 days: 6,127 profiles existed with almost nothing linking into
    or out of them, which is what these edges are for.
    """
    name = _esc(r["program"])
    slug = r.get("major")
    return f'<a class="tw-prog" href="/majors/{_esc(slug)}/">{name}</a>' if slug else name


GRAD_LEVELS = ("4", "5", "6", "7", "8")


def payback_text(r: dict) -> str | None:
    """Median debt over the yearly earnings gain. Mirrored by _paybackCell in site/components/table.js.

    A program whose graduates earn no more than a high-school graduate has no gain to set against
    its debt. That is a known answer, not missing data, so it says so instead of "insufficient data".
    """
    if r["payback"] is not None:
        return f"{r['payback']:.1f} yrs"
    if r["verdict"] == "fail" and r.get("debt") is not None:
        return '<span class="tw-td__insuf">no earnings gain</span>'
    return None


def verdict_chip(r: dict) -> str:
    """The verdict cell. Mirrored exactly by _verdictCell in site/components/table.js."""
    if r["verdict"] == "insufficient":
        return '<span class="tw-verdict tw-verdict--insuf">insufficient data</span>'
    if r["verdict"] == "nobench":
        return '<span class="tw-verdict tw-verdict--insuf">no state benchmark</span>'
    if r.get("grad"):
        word = "above" if r["verdict"] == "pass" else "below"
        mod = "pass" if r["verdict"] == "pass" else "fail"
        return f'<span class="tw-verdict tw-verdict--{mod}">{word} HS line</span>'
    if r["verdict"] == "pass":
        return '<span class="tw-verdict tw-verdict--pass">clears the bar</span>'
    return '<span class="tw-verdict tw-verdict--fail">falls short</span>'


def _static_row(r: dict) -> str:
    """One <tr> of static, crawlable HTML using the final component classes."""

    def cell(label, val, num=False):
        cls = "tw-td tw-td--num" if num else "tw-td"
        inner = val if val is not None else '<span class="tw-td__insuf">insufficient data</span>'
        return f'<td class="{cls}" data-label="{label}">{inner}</td>'

    verdict = verdict_chip(r)
    prem = None
    if r["premium"] is not None:
        sign = "+" if r["premium"] >= 0 else "-"
        prem = f"{sign}{_money(abs(r['premium']))}"
    # 1-year earnings marker: only beside a DISPLAYED assessed value whose horizon is 1-year. Horizon is
    # None for insufficient rows (earnings hidden), so this never labels a figure the page does not show.
    earn = _money(r["earnings"])
    if earn is not None:
        marker = (
            '<span class="tw-oneyr">1-year earnings</span>'
            if r.get("horizon") == "1yr_after_completion"
            else ""
        )
        # One container, so the mobile row is label + value and not label + value + marker:
        # as a third flex item the nowrap marker could not shrink, and pushed the document
        # 34px past a 320px viewport on a school with any 1-year figure.
        earn = f'<span class="tw-val">{earn}{marker}</span>'
    return (
        f'<tr class="tw-tr{" tw-tr--insuf" if r["verdict"] == "insufficient" else ""}">'
        f'<th scope="row" class="tw-td tw-td--program" data-label="Program">'
        f"{_program_cell(r)}</th>"
        f'<td class="tw-td" data-label="Degree">{_esc(r["credential"] or "")}</td>'
        + cell("Median earnings", earn, True)
        + cell("vs a high-school grad", prem, True)
        + f'<td class="tw-td" data-label="Verdict">{verdict}</td>'
        + cell("Median debt", _money(r["debt"]), True)
        + cell("Debt as years of gain", payback_text(r), True)
        + cell(
            "Recent completers",
            None if r["completers"] is None else format(r["completers"], ","),
            True,
        )
        + "</tr>"
    )


HEAD = (
    '<th scope="col" class="tw-th">Program</th><th scope="col" class="tw-th">Degree</th>'
    '<th scope="col" class="tw-th tw-th--num">Median earnings</th>'
    '<th scope="col" class="tw-th tw-th--num">vs a high-school grad</th>'
    '<th scope="col" class="tw-th">Verdict</th>'
    '<th scope="col" class="tw-th tw-th--num">Median debt</th>'
    '<th scope="col" class="tw-th tw-th--num">Debt as years of gain</th>'
    '<th scope="col" class="tw-th tw-th--num">Recent completers</th>'
)


def build_profile(meta: dict, rows: list[dict], threshold: int) -> tuple[str, str | None]:
    """Return (static HTML, tail JSON or None). Static core carries up to `threshold` program rows."""
    decided = sum(1 for r in rows if r["verdict"] != "insufficient")
    total = len(rows)
    static_rows = rows[:threshold]
    tail = rows[threshold:]
    body = "".join(_static_row(r) for r in static_rows)
    tail_json = _island_json({"programs": tail}) if tail else None

    # Progressive-enhancement contract (components/profile.js): the static table is the crawlable,
    # no-JS baseline; the JSON island carries the same static rows as data so the script can upgrade
    # the table to sortable without re-fetching, and data-tail/data-remaining drive "Show all N".
    island = _island_json(
        {
            "rows": static_rows,
            "coverage": {"measured": decided, "total": total},
            "caption": "Programs by earnings versus a state high-school graduate.",
        }
    )
    profile_attrs = (
        f'data-tw-profile data-tail="programs-tail.json" data-remaining="{len(tail)}"'
        if tail
        else "data-tw-profile"
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(meta["name"])}: what families pay and what graduates earn</title>
<link rel="canonical" href="https://truewise.dev/college/{_slug(meta["name"])}/">
<link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/components.css"></head>
<body><main class="wrap">
<h1>{_esc(meta["name"])}</h1>
<p class="profile-sub">{_esc(meta["state"])} · {_esc(meta["control"])}</p>
<div {profile_attrs}>
<script type="application/json" class="tw-profile-data">{island}</script>
<div class="tw-profile-static">
<p class="tw-coverage"><b>{decided} of {total}</b> programs could be assessed
<span class="tw-coverage__note">{round(100 * decided / total)}% have an earnings verdict</span></p>
<div class="tw-table__scroll" tabindex="0" role="region" aria-label="Programs and earnings"><table class="tw-table">
<caption class="tw-table__caption">Programs by earnings versus a state high-school graduate.</caption>
<thead><tr>{HEAD}</tr></thead><tbody>{body}</tbody></table></div>
</div></div>
<p class="tw-source">Source: U.S. Department of Education College Scorecard. Suppressed values are shown
as insufficient data, never imputed. Figures describe past graduates and are never a promise.</p>
<script src="/components/table.js"></script><script src="/components/profile.js"></script>
</main></body></html>"""
    return html, tail_json


def _gz(s: str) -> int:
    return len(gzip.compress(s.encode()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ap.add_argument(
        "--preview",
        action="store_true",
        help="assemble pilot/_preview/ (with assets) so the pages can be served for browser tests",
    )
    args = ap.parse_args()
    con = duckdb.connect()

    print(f"Canonical-profile pilot (static threshold = {args.threshold} programs)\n")
    print(
        f"{'case':18} {'total':>5} {'static':>6} {'tail':>5} "
        f"{'html KB':>8} {'html gz':>8} {'tail gz':>8} {'all-static gz':>13}"
    )
    measurements = []
    for case, unitid in REPS.items():
        meta, rows = _rows_for(con, unitid)
        html, tail_json = build_profile(meta, rows, args.threshold)
        all_html, _ = build_profile(meta, rows, 10**9)  # everything static, for comparison
        slug = _slug(meta["name"])
        d = OUT / "college" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html)
        if tail_json:
            (d / "programs-tail.json").write_text(tail_json)
        m = {
            "case": case,
            "total": len(rows),
            "static": min(args.threshold, len(rows)),
            "tail": max(0, len(rows) - args.threshold),
            "html_kb": round(len(html) / 1024, 1),
            "html_gz_kb": round(_gz(html) / 1024, 1),
            "tail_gz_kb": round(_gz(tail_json) / 1024, 1) if tail_json else 0,
            "all_static_gz_kb": round(_gz(all_html) / 1024, 1),
        }
        measurements.append(m)
        print(
            f"{case:18} {m['total']:>5} {m['static']:>6} {m['tail']:>5} "
            f"{m['html_kb']:>8} {m['html_gz_kb']:>8} {m['tail_gz_kb']:>8} {m['all_static_gz_kb']:>13}"
        )
    (OUT / "measurements.json").write_text(json.dumps(measurements, indent=2))
    print(f"\nWrote {len(REPS)} pilot profiles + measurements.json to {OUT.relative_to(ROOT)}/")

    if args.preview:
        _assemble_preview()


def _assemble_preview() -> None:
    """Assemble pilot/_preview/ as a servable root so the rendered pages can be measured in a real
    browser (Lighthouse/axe). The pilot pages use root-absolute asset paths (/styles.css,
    /components.css, /components/*.js, /college/<slug>/), so this gathers those into one root.

    Run `make components` first so the deployable assets exist under site/.
    Serve with:  python -m http.server -d pilot/_preview 8000  then open /college/<slug>/
    """
    import shutil

    preview = OUT / "_preview"
    if preview.exists():
        shutil.rmtree(preview)
    (preview / "components").mkdir(parents=True, exist_ok=True)
    # Assets from the deployed site tree (built by build_tokens + build_components).
    for rel in ("styles.css", "components.css"):
        src = SITE / rel
        if src.exists():
            shutil.copyfile(src, preview / rel)
    comp = SITE / "components"
    if comp.exists():
        for js in comp.glob("*.js"):
            shutil.copyfile(js, preview / "components" / js.name)
    # The rendered profiles.
    shutil.copytree(OUT / "college", preview / "college", dirs_exist_ok=True)
    print(
        f"preview assembled at {preview.relative_to(ROOT)}/\n"
        f"  serve: python -m http.server -d {preview.relative_to(ROOT)} 8000\n"
        "  then open a profile, e.g. http://localhost:8000/college/"
        "pennsylvania-state-university-main-campus/"
    )


if __name__ == "__main__":
    main()
