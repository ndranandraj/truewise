"""Generate the static JSON that powers the K-12 advanced-course-access pages.

Reads data/parquet/k12.parquet (built by build_k12_source from the CRDC) and writes, under
site/k12/data/:
  * index.json          - one light entry per high school (search index + offer flags)
  * schools/<STATE>.json - that state's high schools, keyed by CRDC COMBOKEY, with full detail

For each school we report whether it offers AP, calculus, and physics, how many students take
each, the participation rate (share of the school's students taking the course), and how many
of the three advanced tracks the school offers at all. Counts a school withheld or that were
too small to report are shown as unavailable, never guessed.

Usage (from repo root, after build_k12_source has produced k12.parquet):
    python -m pipeline.build_k12
"""

from __future__ import annotations

import json
from collections import defaultdict

import duckdb

from pipeline.config import PARQUET_DIR, ROOT

OUT_DIR = ROOT / "site" / "k12" / "data"


def _int(x):
    return None if x is None else int(round(x))


def main() -> None:
    src = PARQUET_DIR / "k12.parquet"
    if not src.exists():
        raise SystemExit("No k12.parquet, run `python -m pipeline.build_k12_source` first.")
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT combokey, coalesce(state, 'ZZ') AS state, name, district, charter, magnet,
               enroll_total, offers_ap, ap_courses, ap_enroll,
               offers_calc, calc_enroll, offers_physics, phys_enroll
        FROM read_parquet('{src}')
        WHERE name IS NOT NULL AND enroll_total > 0
        ORDER BY name
        """
    ).fetchall()

    def _rate(part, whole):
        # Share of students taking a course, only where it is offered and has enrollment.
        return round(100 * part / whole) if part and whole else None

    index = []
    by_state: dict[str, dict] = defaultdict(dict)
    for r in rows:
        (
            combokey,
            state,
            name,
            district,
            charter,
            magnet,
            enroll,
            offers_ap,
            ap_courses,
            ap_enroll,
            offers_calc,
            calc_enroll,
            offers_phys,
            phys_enroll,
        ) = r

        # How many of the three advanced tracks the school offers (0-3).
        breadth = int(bool(offers_ap)) + int(bool(offers_calc)) + int(bool(offers_phys))

        by_state[state][combokey] = {
            "name": name,
            "district": district,
            "state": state,
            "charter": bool(charter),
            "magnet": bool(magnet),
            "enroll": _int(enroll),
            "breadth": breadth,
            "ap": {
                "offered": bool(offers_ap),
                "courses": _int(ap_courses),
                "enroll": _int(ap_enroll),
                "rate": _rate(ap_enroll, enroll),  # % of students taking at least one AP course
            },
            "calc": {
                "offered": bool(offers_calc),
                "enroll": _int(calc_enroll),
                "rate": _rate(calc_enroll, enroll),
            },
            "phys": {
                "offered": bool(offers_phys),
                "enroll": _int(phys_enroll),
                "rate": _rate(phys_enroll, enroll),
            },
        }
        index.append(
            {
                "k": combokey,
                "n": name,
                "s": state,
                "d": district,
                "ap": bool(offers_ap),
                "c": bool(offers_calc),
                "p": bool(offers_phys),
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "schools").mkdir(exist_ok=True)
    (OUT_DIR / "index.json").write_text(
        json.dumps(
            {"generated": True, "vintage": "2020-21", "schools": index}, separators=(",", ":")
        )
    )
    for state, schools in by_state.items():
        (OUT_DIR / "schools" / f"{state}.json").write_text(
            json.dumps(schools, separators=(",", ":"))
        )

    print(f"high schools: {len(index):,}  |  state files: {len(by_state)}")
    print(f"wrote -> {OUT_DIR}")


if __name__ == "__main__":
    main()
