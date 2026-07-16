"""Tests for the K-12 (CRDC advanced-course-access) extractor and site builder.

No download: tiny synthetic CRDC CSVs exercise the real extraction SQL (including the
suppressed-total handling and the high-school filter), and a synthetic k12 parquet exercises
the access-gap math in build_k12.
"""

from __future__ import annotations

import csv
import json

import duckdb

import pipeline.build_k12 as bk
import pipeline.build_k12_source as bks

RACES = bks.RACES


def _write(path, rows):
    cols = sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "0") for c in cols})


def _enr(**vals):
    r = {"COMBOKEY": vals["COMBOKEY"]}
    for race in RACES:
        for s in ("M", "F"):
            r[f"SCH_ENR_{race}_{s}"] = "0"
    r.update({k: v for k, v in vals.items() if k != "COMBOKEY"})
    return r


def _mk_crdc(folder):
    # One high school (grade 12) that is 50% Black/Hispanic, with a suppressed female total.
    _write(
        folder / "School Characteristics.csv",
        [
            {
                "COMBOKEY": "HS1",
                "LEA_STATE": "TX",
                "SCH_NAME": "Test High",
                "LEA_NAME": "Test ISD",
                "SCH_STATUS_CHARTER": "No",
                "SCH_STATUS_MAGNET": "No",
                "SCH_GRADE_G09": "No",
                "SCH_GRADE_G10": "No",
                "SCH_GRADE_G11": "No",
                "SCH_GRADE_G12": "Yes",
            },
            {
                "COMBOKEY": "ES1",
                "LEA_STATE": "TX",
                "SCH_NAME": "Test Elementary",
                "LEA_NAME": "Test ISD",
                "SCH_STATUS_CHARTER": "No",
                "SCH_STATUS_MAGNET": "No",
                "SCH_GRADE_G09": "No",
                "SCH_GRADE_G10": "No",
                "SCH_GRADE_G11": "No",
                "SCH_GRADE_G12": "No",
            },
        ],
    )
    # 100 White + 50 Black + 50 Hispanic = 200 total, 100 Black/Hispanic. TOT_ENR_F suppressed.
    _write(
        folder / "Enrollment.csv",
        [
            _enr(
                COMBOKEY="HS1",
                SCH_ENR_WH_M="100",
                SCH_ENR_BL_M="50",
                SCH_ENR_HI_M="50",
                TOT_ENR_M="200",
                TOT_ENR_F="-11",
            ),
            _enr(COMBOKEY="ES1", SCH_ENR_WH_M="300"),
        ],
    )
    # AP: 40 students in AP out of 200 enrolled -> 20% participation.
    ap = {
        "COMBOKEY": "HS1",
        "SCH_APENR_IND": "Yes",
        "SCH_APCOURSES": "8",
        "SCH_APENR_WH_M": "30",
        "SCH_APENR_BL_M": "5",
        "SCH_APENR_HI_M": "5",
    }
    for race in RACES:
        for s in ("M", "F"):
            ap.setdefault(f"SCH_APENR_{race}_{s}", "0")
    _write(
        folder / "Advanced Placement.csv",
        [ap, {"COMBOKEY": "ES1", "SCH_APENR_IND": "No", "SCH_APCOURSES": "-9"}],
    )
    calc = {"COMBOKEY": "HS1", "SCH_MATHCLASSES_CALC": "2", "SCH_MATHENR_CALC_WH_M": "20"}
    for race in RACES:
        for s in ("M", "F"):
            calc.setdefault(f"SCH_MATHENR_CALC_{race}_{s}", "0")
    _write(folder / "Calculus.csv", [calc, {"COMBOKEY": "ES1", "SCH_MATHCLASSES_CALC": "0"}])
    phys = {"COMBOKEY": "HS1", "SCH_SCICLASSES_PHYS": "0"}
    for race in RACES:
        for s in ("M", "F"):
            phys.setdefault(f"SCH_SCIENR_PHYS_{race}_{s}", "0")
    _write(folder / "Physics.csv", [phys, {"COMBOKEY": "ES1", "SCH_SCICLASSES_PHYS": "0"}])


def test_source_extracts_high_schools_with_suppressed_total(tmp_path):
    _mk_crdc(tmp_path)
    con = duckdb.connect()
    bks.build(con, tmp_path)
    rows = con.execute("SELECT * FROM k12").fetchdf().to_dict("records")
    assert len(rows) == 1  # elementary excluded
    hs = rows[0]
    assert hs["combokey"] == "HS1"
    assert hs["enroll_total"] == 200  # summed from race components, not the suppressed total
    assert hs["offers_ap"] and hs["ap_courses"] == 8 and hs["ap_enroll"] == 40
    assert hs["offers_calc"] and hs["calc_enroll"] == 20
    assert not hs["offers_physics"]


def test_build_k12_participation_and_breadth(tmp_path, monkeypatch):
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = duckdb.connect()
    con.execute(
        """CREATE TABLE k12 AS SELECT * FROM (VALUES
        ('HS1','TX','Test High','Test ISD',false,false,200.0,true,8.0,40.0,true,20.0,false,0.0))
        t(combokey,state,name,district,charter,magnet,enroll_total,offers_ap,
          ap_courses,ap_enroll,offers_calc,calc_enroll,offers_physics,phys_enroll)"""
    )
    con.execute(f"COPY k12 TO '{pq / 'k12.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bk, "PARQUET_DIR", pq)
    monkeypatch.setattr(bk, "OUT_DIR", tmp_path / "k12-data")
    bk.main()

    tx = json.loads((tmp_path / "k12-data" / "schools" / "TX.json").read_text())
    s = tx["HS1"]
    assert s["ap"]["enroll"] == 40 and s["ap"]["courses"] == 8
    assert s["ap"]["rate"] == 20  # 40 of 200 students take AP
    assert s["calc"]["offered"] and s["calc"]["rate"] == 10 and not s["phys"]["offered"]
    assert s["breadth"] == 2  # AP + calculus, no physics
    idx = json.loads((tmp_path / "k12-data" / "index.json").read_text())
    assert idx["vintage"] == "2020-21" and idx["schools"][0]["k"] == "HS1"
