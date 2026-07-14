"""National + state Value Check summary — the headline numbers and local-press hook.

Reads data/parquet/value_check.parquet and writes a small JSON summary
(site/data/value_check_summary.json) plus prints headlines. Runs on local files.

Usage (from repo root):
    python -m analysis.summary
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from pipeline.config import PARQUET_DIR, ROOT

OUT = ROOT / "site" / "data" / "value_check_summary.json"


def main() -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet — run the pipeline first.")
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

    worst_cip = con.execute(
        """
        SELECT left(cip_code, 2) AS cip2, any_value(cip_desc) AS example,
               count(*) FILTER (WHERE value_flag = 'fails_earnings_premium') AS fails,
               count(*) FILTER (WHERE value_flag != 'insufficient_data')      AS decided
        FROM v WHERE cip_code IS NOT NULL GROUP BY cip2
        HAVING decided >= 100 ORDER BY fails * 1.0 / decided DESC LIMIT 10
        """
    ).fetchall()

    summary = {
        "generated_from": "College Scorecard Field-of-Study + Institution (most recent)",
        "programs_total": total,
        "programs_decided": decided,
        "programs_insufficient_data": total - decided,
        "programs_fail_earnings_premium": fails,
        "programs_pass_earnings_premium": passes,
        "fail_rate_among_decided": round(fails / decided, 4) if decided else None,
        "by_state": [
            {"state": s, "fails": f, "decided": d, "fail_rate": round(f / d, 4)}
            for s, f, d in by_state
        ],
        "highest_fail_rate_fields": [
            {"cip2": c, "example": ex, "fails": f, "decided": d, "fail_rate": round(f / d, 4)}
            for c, ex, f, d in worst_cip
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))

    print(f"programs: {total:,}  decided: {decided:,}  "
          f"fail EP: {fails:,} ({100 * fails / decided:.1f}% of decided)")
    print("\nTop 5 states by count of programs failing the earnings-premium test:")
    for s, f, d in by_state[:5]:
        print(f"  {s}: {f:,} programs fail ({100 * f / d:.0f}% of {d:,} decided)")
    print("\nFields of study with the highest fail rates (>=100 decided programs):")
    for c, ex, f, d in worst_cip[:5]:
        print(f"  CIP {c} {ex[:32]:32s} {100 * f / d:.0f}% fail ({f:,}/{d:,})")
    print(f"\nWrote -> {OUT}")


if __name__ == "__main__":
    main()
