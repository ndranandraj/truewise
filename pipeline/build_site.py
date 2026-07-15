"""Generate the static JSON that powers the Value Check site pages.

Reads data/parquet/value_check.parquet and writes, under site/value-check/data/:
  * schools.json          - one entry per school (search index + headline counts)
  * programs/<STATE>.json  - that state's programs, grouped by UNITID, with flags

State-sharding keeps the file count small (~50) and each file a reasonable size,
so the whole thing serves statically with no backend. The web app loads schools.json
once for search, then fetches a single state file when a school is opened.

Usage (from repo root, after the pipeline has produced value_check.parquet):
    python -m pipeline.build_site
"""

from __future__ import annotations

import json
from collections import defaultdict

import duckdb

from pipeline.config import PARQUET_DIR, ROOT

OUT_DIR = ROOT / "site" / "value-check" / "data"


def _round(x, n=0):
    if x is None:
        return None
    return int(round(x)) if n == 0 else round(x, n)


def main() -> None:
    vc = PARQUET_DIR / "value_check.parquet"
    if not vc.exists():
        raise SystemExit("No value_check.parquet — run the pipeline first.")
    con = duckdb.connect()
    # Real institutions only (numeric UNITID); Scorecard also carries national
    # aggregate rows we don't want as "schools".
    rows = con.execute(
        f"""
        SELECT unitid, inst_name, coalesce(state, 'ZZ') AS state, control,
               cip_code, cip_desc, credential_level, credential_desc,
               completers_count, earnings, earnings_horizon,
               earnings_threshold_state, earnings_premium_state,
               debt_median, debt_to_earnings_ratio,
               value_flag
        FROM read_parquet('{vc}')
        WHERE regexp_matches(unitid, '^[0-9]+$')
        ORDER BY inst_name, cip_desc, credential_level
        """
    ).fetchall()

    schools: dict[str, dict] = {}
    by_state: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for r in rows:
        (
            unitid,
            name,
            state,
            control,
            cip,
            cip_desc,
            credlev,
            cred_desc,
            completers,
            earn,
            horizon,
            thr,
            prem,
            debt,
            dte,
            flag,
        ) = r
        if unitid is None:
            continue
        s = schools.setdefault(
            unitid,
            {
                "unitid": unitid,
                "name": name,
                "state": state,
                "control": control,
                "threshold": None,  # per-school (state HS-grad benchmark); dedupes off programs
                "n_programs": 0,
                "n_fail": 0,
                "n_pass": 0,
                "n_insufficient": 0,
            },
        )
        if s["threshold"] is None and thr is not None:
            s["threshold"] = _round(thr)
        s["n_programs"] += 1
        s["n_fail"] += flag == "fails_earnings_premium"
        s["n_pass"] += flag == "passes_earnings_premium"
        s["n_insufficient"] += flag == "insufficient_data"

        # Shards carry only decided programs (keeps the payload small); the index
        # counts above still tell each school how many are insufficient-data.
        if flag == "insufficient_data":
            continue
        by_state[state][unitid].append(
            {
                "cip": cip,
                "program": cip_desc,
                "credential": cred_desc,
                "flag": flag,
                "earnings": _round(earn),
                "horizon": horizon,
                "debt": _round(debt),
                "debt_to_earnings": _round(dte, 3),
                "completers": _round(completers),
            }
        )

    # Merge school identity (city, enrollment, url) from the institutions table.
    inst_path = PARQUET_DIR / "institutions.parquet"
    if inst_path.exists():
        ident = {
            r[0]: r[1:]
            for r in con.execute(
                f"SELECT unitid, city, school_url, enrollment FROM read_parquet('{inst_path}')"
            ).fetchall()
        }
        for s in schools.values():
            city, url, enr = ident.get(s["unitid"], (None, None, None))
            s["city"] = city
            s["url"] = url
            s["enrollment"] = int(enr) if enr else None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "programs").mkdir(exist_ok=True)

    index = sorted(schools.values(), key=lambda x: (x["name"] or "").lower())
    (OUT_DIR / "schools.json").write_text(
        json.dumps({"generated": True, "schools": index}, separators=(",", ":"))
    )
    prog_dir = OUT_DIR / "programs"
    for state, by_school in by_state.items():
        (prog_dir / f"{state}.json").write_text(json.dumps(by_school, separators=(",", ":")))
    # Neutralize any stale state file from a previous run that has no data now.
    for existing in prog_dir.glob("*.json"):
        if existing.stem not in by_state:
            existing.write_text("{}")

    print(f"schools: {len(index):,}  |  state files: {len(by_state)}")
    print(f"wrote -> {OUT_DIR}")


if __name__ == "__main__":
    main()
