"""National + state Value Check summary, the headline numbers and local-press hook.

Reads data/parquet/value_check.parquet and writes a small JSON summary
(site/data/value_check_summary.json) plus prints headlines. Runs on local files.

Usage (from repo root):
    python -m analysis.summary
"""

from __future__ import annotations

import json

import duckdb

from pipeline.config import PARQUET_DIR, ROOT
from pipeline.program_unit import programs_sql, undergrad

OUT = ROOT / "site" / "data" / "value_check_summary.json"


def main() -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con = duckdb.connect()
    # Every figure counts a program once (see pipeline/program_unit.py). The headline population is
    # undergraduate programs: certificates, associate's and bachelor's, which the federal test
    # compares with high-school graduates. The per-campus and all-credential figures are kept for
    # the correction note and the methodology.
    con.execute(f"CREATE VIEW allp AS SELECT * FROM {programs_sql(vc)}")
    con.execute(f"CREATE VIEW v AS SELECT * FROM allp WHERE {undergrad()}")
    con.execute(f"CREATE VIEW rows AS SELECT * FROM read_parquet('{vc}')")

    def one(sql):
        return con.execute(sql).fetchone()

    total = one("SELECT count(*) FROM v")[0]
    decided = one("SELECT count(*) FROM v WHERE value_flag != 'insufficient_data'")[0]
    fails = one("SELECT count(*) FROM v WHERE value_flag = 'fails_earnings_premium'")[0]
    passes = decided - fails
    with_earnings = one("SELECT count(*) FROM v WHERE earnings IS NOT NULL")[0]
    d4, f4 = one(
        "SELECT count(*) FILTER (WHERE value_flag != 'insufficient_data'), "
        "count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') "
        "FROM v WHERE earnings_horizon = '4yr_after_completion'"
    )
    fails_1yr = one(
        "SELECT count(*) FROM v WHERE value_flag = 'fails_earnings_premium' "
        "AND earnings_horizon = '1yr_after_completion'"
    )[0]
    cosm_f, cosm_d = one(
        "SELECT count(*) FILTER (WHERE value_flag = 'fails_earnings_premium'), "
        "count(*) FILTER (WHERE value_flag != 'insufficient_data') FROM v WHERE cip_code = '1204'"
    )
    median_premium = one(
        "SELECT median(earnings / earnings_threshold_state - 1) FROM v "
        "WHERE value_flag != 'insufficient_data'"
    )[0]
    all_decided, all_fails, all_total = one(
        "SELECT count(*) FILTER (WHERE value_flag != 'insufficient_data'), "
        "count(*) FILTER (WHERE value_flag = 'fails_earnings_premium'), count(*) FROM allp"
    )
    grad_decided, grad_fails = one(
        "SELECT count(*) FILTER (WHERE value_flag != 'insufficient_data'), "
        "count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') FROM allp "
        f"WHERE NOT ({undergrad()})"
    )
    row_decided, row_fails, row_total = one(
        "SELECT count(*) FILTER (WHERE value_flag != 'insufficient_data'), "
        "count(*) FILTER (WHERE value_flag = 'fails_earnings_premium'), count(*) FROM rows"
    )
    shared_groups = one(
        "SELECT count(*) FROM allp WHERE n_campuses > 1 AND value_flag != 'insufficient_data'"
    )[0]

    by_state = con.execute(
        """
        SELECT state,
               count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') AS fails,
               count(*) FILTER (WHERE value_flag != 'insufficient_data')      AS decided
        FROM v WHERE state IS NOT NULL GROUP BY state HAVING decided > 0 ORDER BY fails DESC, state
        """
    ).fetchall()

    # Group at the 4-digit CIP so the label matches the field (grouping at 2 digits and
    # labelling with any member's description mislabelled families, e.g. tagging the whole
    # CIP-12 family as "cosmetology").
    worst_cip = con.execute(
        """
        SELECT cip_code AS cip, any_value(cip_desc) AS example,
               count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') AS fails,
               count(*) FILTER (WHERE value_flag != 'insufficient_data')      AS decided
        FROM v WHERE cip_code IS NOT NULL GROUP BY cip_code
        HAVING decided >= 100 ORDER BY fails * 1.0 / decided DESC, cip LIMIT 10
        """
    ).fetchall()

    # Sensitivity to the obvious criticism: only about a quarter of programs report earnings, and
    # suppression is not random. Post-stratify: assume each suppressed program fails at the rate
    # observed in its own credential x sector cell, and re-estimate across all programs. This only
    # corrects for credential and sector mix, not for differences within a cell. Also report the
    # rate weighted by graduates, because "programs" and "graduates" are different claims.
    strat = one(
        """
        WITH cell AS (
          SELECT credential_desc, control,
                 count(*) FILTER (WHERE value_flag != 'insufficient_data') AS rep,
                 count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') AS fail,
                 count(*) FILTER (WHERE value_flag = 'insufficient_data') AS sup
          FROM v WHERE control IS NOT NULL AND regexp_matches(unitid, '^[0-9]+$')
          GROUP BY 1, 2)
        SELECT sum(fail + sup * (fail * 1.0 / nullif(rep, 0))) AS est_fail,
               sum(rep + sup) AS all_prog
        FROM cell WHERE rep > 0
        """
    )
    students = one(
        """
        SELECT sum(completers_count) FILTER (WHERE value_flag = 'fails_earnings_premium'),
               sum(completers_count) FILTER (WHERE value_flag != 'insufficient_data')
        FROM v WHERE completers_count IS NOT NULL AND regexp_matches(unitid, '^[0-9]+$')
        """
    )
    poststrat_rate = (strat[0] / strat[1]) if strat and strat[1] else None
    student_rate = (students[0] / students[1]) if students and students[1] else None

    r4 = lambda x: round(x, 4) if x is not None else None  # noqa: E731
    summary = {
        "generated_from": "College Scorecard Field-of-Study + Institution (most recent)",
        "population": (
            "undergraduate programs (certificates, associate's, bachelor's), each counted once per "
            "OPEID6 x 4-digit CIP x credential"
        ),
        "programs_total": total,
        "programs_with_earnings": with_earnings,
        "programs_decided": decided,
        "programs_insufficient_data": total - decided,
        "programs_fail_earnings_premium": fails,
        "programs_pass_earnings_premium": passes,
        "fail_rate_among_decided": r4(fails / decided) if decided else None,
        "median_premium_among_decided": r4(median_premium),
        "four_year_only": {"decided": d4, "fails": f4, "fail_rate": r4(f4 / d4) if d4 else None},
        "fails_on_1yr_fallback": fails_1yr,
        "cosmetology_1204": {
            "fails": cosm_f,
            "decided": cosm_d,
            "fail_rate": r4(cosm_f / cosm_d) if cosm_d else None,
        },
        # Robustness of the headline (see the comment above for the method).
        "fail_rate_poststratified_all_programs": r4(poststrat_rate),
        "fail_rate_weighted_by_graduates": r4(student_rate),
        "reference": {
            "all_credentials": {
                "programs_total": all_total,
                "decided": all_decided,
                "fails": all_fails,
                "fail_rate": r4(all_fails / all_decided) if all_decided else None,
            },
            "graduate_credentials": {
                "decided": grad_decided,
                "fails": grad_fails,
            },
            "per_campus_rows_before_2026_09_correction": {
                "rows_total": row_total,
                "decided": row_decided,
                "fails": row_fails,
                "fail_rate": r4(row_fails / row_decided) if row_decided else None,
            },
            "decided_programs_shared_by_several_campuses": shared_groups,
        },
        "by_state": [
            {"state": s, "fails": f, "decided": d, "fail_rate": round(f / d, 4)}
            for s, f, d in by_state
        ],
        "highest_fail_rate_fields": [
            {"cip": c, "example": ex, "fails": f, "decided": d, "fail_rate": round(f / d, 4)}
            for c, ex, f, d in worst_cip
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))

    print(
        f"undergraduate programs (each counted once): {total:,}  decided: {decided:,}  "
        f"fail EP: {fails:,} ({100 * fails / decided:.1f}% of decided)"
    )
    print("\nTop 5 states by count of programs failing the earnings-premium test:")
    for s, f, d in by_state[:5]:
        print(f"  {s}: {f:,} programs fail ({100 * f / d:.0f}% of {d:,} decided)")
    print("\nFields of study with the highest fail rates (>=100 decided programs):")
    for c, ex, f, d in worst_cip[:5]:
        print(f"  CIP {c} {ex[:32]:32s} {100 * f / d:.0f}% fail ({f:,}/{d:,})")
    print(f"\nWrote -> {OUT}")


if __name__ == "__main__":
    main()
