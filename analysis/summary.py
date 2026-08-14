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

OUT = ROOT / "site" / "data" / "value_check_summary.json"


def main() -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet, run the pipeline first.")
    con = duckdb.connect()
    con.execute(f"CREATE VIEW v AS SELECT * FROM read_parquet('{vc}')")

    total = con.execute("SELECT count(*) FROM v").fetchone()[0]
    decided = con.execute(
        "SELECT count(*) FROM v WHERE value_flag != 'insufficient_data'"
    ).fetchone()[0]
    fails = con.execute(
        "SELECT count(*) FROM v WHERE value_flag = 'fails_earnings_premium'"
    ).fetchone()[0]
    passes = decided - fails

    by_state = con.execute(
        """
        SELECT state,
               count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') AS fails,
               count(*) FILTER (WHERE value_flag != 'insufficient_data')      AS decided
        FROM v WHERE state IS NOT NULL GROUP BY state HAVING decided > 0 ORDER BY fails DESC
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
        HAVING decided >= 100 ORDER BY fails * 1.0 / decided DESC LIMIT 10
        """
    ).fetchall()

    # Sensitivity of the headline to the obvious criticism: we only observe ~26% of programs,
    # and suppression is NOT random (undergraduate certificates are ~82% suppressed and fail at
    # ~39%; bachelor's are ~59% suppressed and fail at ~4.5%). So: post-stratify. Assume each
    # suppressed program fails at the rate observed in its own credential x sector cell, and
    # re-estimate across all programs. Also report the rate weighted by graduates rather than by
    # programs, because "1 in 11 programs" and "1 in 11 graduates" are different claims that the
    # public will otherwise conflate.
    strat = con.execute(
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
    ).fetchone()
    students = con.execute(
        """
        SELECT sum(completers_count) FILTER (WHERE value_flag = 'fails_earnings_premium'),
               sum(completers_count) FILTER (WHERE value_flag != 'insufficient_data')
        FROM v WHERE completers_count IS NOT NULL AND regexp_matches(unitid, '^[0-9]+$')
        """
    ).fetchone()
    poststrat_rate = (strat[0] / strat[1]) if strat and strat[1] else None
    student_rate = (students[0] / students[1]) if students and students[1] else None

    summary = {
        "generated_from": "College Scorecard Field-of-Study + Institution (most recent)",
        "programs_total": total,
        "programs_decided": decided,
        "programs_insufficient_data": total - decided,
        "programs_fail_earnings_premium": fails,
        "programs_pass_earnings_premium": passes,
        "fail_rate_among_decided": round(fails / decided, 4) if decided else None,
        # Robustness of the headline (see the comment above for the method).
        "fail_rate_poststratified_all_programs": (
            round(poststrat_rate, 4) if poststrat_rate is not None else None
        ),
        "fail_rate_weighted_by_graduates": (
            round(student_rate, 4) if student_rate is not None else None
        ),
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
        f"programs: {total:,}  decided: {decided:,}  "
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
