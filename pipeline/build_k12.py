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
    cur = con.execute(
        f"""
        SELECT * FROM read_parquet('{src}')
        WHERE name IS NOT NULL AND enroll_total > 0
        ORDER BY name
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]

    def _rate(part, whole):
        # Share of students taking a course, only where it is offered and has enrollment.
        return round(100 * part / whole) if part and whole else None

    def _course(offered, enroll, whole, courses=None):
        d = {"offered": bool(offered), "enroll": _int(enroll), "rate": _rate(enroll, whole)}
        if courses is not None:
            d["courses"] = _int(courses)
        return d

    index = []
    by_state: dict[str, dict] = defaultdict(dict)
    for r in rows:
        state = r["state"] or "ZZ"
        enroll = r["enroll_total"]
        couns, teach, uncert = r["fte_counselors"], r["fte_teachers"], r["fte_teach_uncert"]
        staff = {
            # student-to-counselor ratio; a real reported 0 counselors is meaningful.
            "counselor_ratio": round(enroll / couns) if (couns and enroll) else None,
            "no_counselor": couns == 0,
            "police": bool(r["fte_police"] and r["fte_police"] > 0),
            "guard": bool(r["fte_guards"] and r["fte_guards"] > 0),
            "uncert_pct": round(100 * uncert / teach) if (uncert is not None and teach) else None,
        }
        by_state[state][r["combokey"]] = {
            "name": r["name"],
            "district": r["district"],
            "state": state,
            "charter": bool(r["charter"]),
            "magnet": bool(r["magnet"]),
            "enroll": _int(enroll),
            # How many of the three core advanced tracks the school offers (0-3).
            "breadth3": int(bool(r["offers_ap"]))
            + int(bool(r["offers_calc"]))
            + int(bool(r["offers_physics"])),
            "courses": {
                "ap": _course(r["offers_ap"], r["ap_enroll"], enroll, r["ap_courses"]),
                "calc": _course(r["offers_calc"], r["calc_enroll"], enroll),
                "phys": _course(r["offers_physics"], r["phys_enroll"], enroll),
                "chem": _course(r["offers_chem"], r["chem_enroll"], enroll),
                "cs": _course(r["offers_cs"], r["cs_enroll"], enroll),
                "dual": _course(r["offers_dual"], r["dual_enroll"], enroll),
                "ib": _course(r["offers_ib"], r["ib_enroll"], enroll),
                "gt": _course(r["offers_gt"], r["gt_enroll"], enroll),
            },
            "staff": staff,
        }
        index.append(
            {
                "k": r["combokey"],
                "n": r["name"],
                "s": state,
                "d": r["district"],
                "ap": bool(r["offers_ap"]),
                "c": bool(r["offers_calc"]),
                "p": bool(r["offers_physics"]),
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
