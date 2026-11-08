"""Write a parquet whose row order comes from its data, not from how DuckDB happened to run.

A join with no ORDER BY returns rows in an order that changes with the DuckDB version and the thread
count. The figures stay the same, but the file's checksum moves, and so does anything that reads rows
in file order. Every parquet a refresh writes therefore states a key. A key that repeats is refused:
sorting on it would leave the repeated rows in no fixed order, which is the problem this exists to
remove.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# One row per program as ED publishes it. UNITID + CIP + credential level is not enough: the 10 June
# 2026 Field-of-Study file has 7,020 rows with UNITID "NA", told apart only by OPEID6.
PROGRAM_KEY = "unitid, opeid6, cip_code, credential_level"


def write_sorted_parquet(
    con: duckdb.DuckDBPyConnection, source: str, key: str, out: Path, options: str = ""
) -> None:
    """COPY `source` (a table, or a parenthesized SELECT) to `out` in `key` order."""
    repeats = con.execute(
        f"SELECT {key}, count(*) FROM {source} GROUP BY ALL HAVING count(*) > 1 "
        "ORDER BY ALL LIMIT 3"
    ).fetchall()
    if repeats:
        raise SystemExit(
            f"{out.name}: the sort key ({key}) repeats, for example {repeats}. A new release may have "
            "changed the file's grain: check it, then choose a key that identifies one row."
        )
    fmt = f"FORMAT PARQUET, {options}" if options else "FORMAT PARQUET"
    con.execute(f"COPY (SELECT * FROM {source} ORDER BY {key}) TO '{out}' ({fmt})")
