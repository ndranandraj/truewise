"""FVT/GE Monitor, diff two dated snapshots.

The government publishes only today's program-level numbers and can revise them
silently. Each refresh we archive a compact snapshot (`pipeline.value_check` writes
`archive/fvt/<date>/value_check_snapshot.parquet`); this module compares two of them and
produces a human-readable changelog: programs that newly fail the earnings-premium test,
ones that flipped back to passing, notable earnings revisions, and rows added or removed.

Programs are keyed on UNITID + CIP + credential level. The diff logic lives in
`compute_diff` (unit-tested on synthetic snapshots).

Usage (from repo root):
    python -m pipeline.monitor_diff                 # diff the two most recent snapshots
    python -m pipeline.monitor_diff OLD NEW         # diff two snapshot parquet files
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

from pipeline.config import ARCHIVE_DIR

# A revision in median earnings at least this large is worth flagging.
EARNINGS_DELTA = 1000


def compute_diff(con: duckdb.DuckDBPyConnection) -> dict:
    """Diff `old` and `new` tables (both with the snapshot columns) on `con`."""
    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW joined AS
        SELECT
            COALESCE(o.unitid, n.unitid)                     AS unitid,
            COALESCE(o.cip_code, n.cip_code)                 AS cip_code,
            COALESCE(o.credential_desc, n.credential_desc)   AS credential_desc,
            COALESCE(o.inst_name, n.inst_name)               AS inst_name,
            o.value_flag AS old_flag, n.value_flag AS new_flag,
            o.earnings   AS old_earnings, n.earnings AS new_earnings
        FROM old o FULL OUTER JOIN new n
          ON o.unitid = n.unitid AND o.cip_code = n.cip_code
         AND o.credential_level = n.credential_level
        """
    )

    def rows(where: str) -> list[dict]:
        cols = (
            "inst_name, credential_desc, cip_code, old_flag, new_flag, old_earnings, new_earnings"
        )
        return [
            dict(
                zip(
                    [
                        "inst_name",
                        "credential",
                        "cip",
                        "old_flag",
                        "new_flag",
                        "old_earn",
                        "new_earn",
                    ],
                    r,
                    strict=True,
                )
            )
            for r in con.execute(f"SELECT {cols} FROM joined WHERE {where}").fetchall()
        ]

    newly_failing = rows(
        "old_flag IS DISTINCT FROM 'fails_earnings_premium' "
        "AND new_flag = 'fails_earnings_premium' AND old_flag IS NOT NULL"
    )
    newly_passing = rows(
        "old_flag = 'fails_earnings_premium' AND new_flag = 'passes_earnings_premium'"
    )
    added = rows("old_flag IS NULL")
    removed = rows("new_flag IS NULL")
    revised = rows(
        f"old_earnings IS NOT NULL AND new_earnings IS NOT NULL "
        f"AND abs(new_earnings - old_earnings) >= {EARNINGS_DELTA}"
    )
    return {
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
        "added": added,
        "removed": removed,
        "earnings_revised": revised,
    }


def _load(con: duckdb.DuckDBPyConnection, name: str, path: Path) -> None:
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet('{path}')")


def _latest_two_snapshots() -> tuple[Path, Path]:
    snaps = sorted(ARCHIVE_DIR.glob("*/value_check_snapshot.parquet"))
    if len(snaps) < 2:
        raise SystemExit(
            f"Need at least two snapshots in {ARCHIVE_DIR}; found {len(snaps)}. "
            "Diffs begin once a second monthly snapshot lands."
        )
    return snaps[-2], snaps[-1]


def render_markdown(diff: dict, old_label: str, new_label: str) -> str:
    lines = [f"# FVT Monitor changelog, {old_label} → {new_label}", ""]
    for key, title in [
        ("newly_failing", "Newly failing the earnings-premium test"),
        ("newly_passing", "Newly passing (recovered)"),
        ("earnings_revised", "Notable earnings revisions"),
        ("added", "New programs"),
        ("removed", "Removed programs"),
    ]:
        items = diff[key]
        lines.append(f"## {title} ({len(items)})")
        for r in items[:50]:
            note = ""
            if key == "earnings_revised":
                note = f" (${int(r['old_earn']):,} → ${int(r['new_earn']):,})"
            lines.append(f"- {r['inst_name']}, {r['credential']} (CIP {r['cip']}){note}")
        if len(items) > 50:
            lines.append(f"- …and {len(items) - 50} more")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) == 3:
        old_path, new_path = Path(sys.argv[1]), Path(sys.argv[2])
    else:
        old_path, new_path = _latest_two_snapshots()
    con = duckdb.connect()
    _load(con, "old", old_path)
    _load(con, "new", new_path)
    diff = compute_diff(con)
    old_label, new_label = old_path.parent.name, new_path.parent.name
    md = render_markdown(diff, old_label, new_label)

    out_dir = ARCHIVE_DIR / "diffs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{old_label}_to_{new_label}.md"
    out.write_text(md)
    for key in ("newly_failing", "newly_passing", "earnings_revised", "added", "removed"):
        print(f"  {key:18s} {len(diff[key]):>6,}")
    print(f"\nchangelog -> {out}")


if __name__ == "__main__":
    main()
