"""Generate the data bundled inside the `truewise-data` pip package.

Reads data/parquet/value_check.parquet and writes, into the package's data dir:
  * value_check.parquet - clean program-level table (real institutions only)
  * summary.json        - national + state summary (copied from the site build)
  * meta.json           - dataset version + provenance

Keeping the bundled data small (compact columns, decided + insufficient) means the
package installs offline with no download. Run after the pipeline + summary.

Usage (from repo root):
    python -m pipeline.build_package_data
"""

from __future__ import annotations

import datetime as dt
import json
import shutil

import duckdb

from pipeline.config import PARQUET_DIR, ROOT

PKG_DATA = ROOT / "packages" / "truewise-data" / "truewise_data" / "data"
SCORECARD_RELEASE = "2026-06-10"  # College Scorecard bulk release the data derives from

COLUMNS = [
    "unitid",
    "opeid6",
    "inst_name",
    "state",
    "control",
    "cip_code",
    "cip_desc",
    "credential_level",
    "credential_desc",
    "completers_count",
    "earnings",
    "earnings_horizon",
    "earnings_threshold_state",
    "earnings_threshold_national",
    "earnings_premium_state",
    "earnings_premium_national",
    "fails_ep_state",
    "value_flag",
    "share_earning_above_hs_grad",
    "debt_median",
    "debt_to_earnings_ratio",
]


def main() -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet — run the pipeline first.")
    PKG_DATA.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    out = PKG_DATA / "value_check.parquet"
    con.execute(
        f"""
        COPY (
            SELECT {", ".join(COLUMNS)}
            FROM read_parquet('{vc}')
            WHERE regexp_matches(unitid, '^[0-9]+$')
        ) TO '{out}' (FORMAT PARQUET, COMPRESSION zstd)
        """
    )
    n = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()[0]

    summary_src = ROOT / "site" / "data" / "value_check_summary.json"
    if summary_src.exists():
        shutil.copyfile(summary_src, PKG_DATA / "summary.json")

    (PKG_DATA / "meta.json").write_text(
        json.dumps(
            {
                "dataset": "truewise-value-check",
                "scorecard_release": SCORECARD_RELEASE,
                "generated": dt.date.today().isoformat(),
                "rows": n,
                "source": "U.S. Dept. of Education College Scorecard (Field-of-Study + Institution)",
                "license": "CC-BY-4.0",
                "homepage": "https://truewise.dev",
            },
            indent=2,
        )
    )
    print(f"bundled {n:,} rows -> {out}")
    print(f"wrote -> {PKG_DATA}/summary.json, meta.json")


if __name__ == "__main__":
    main()
