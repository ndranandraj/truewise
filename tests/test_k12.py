"""Tests for the K-12 (CRDC) extractor and site builder.

No download: tiny synthetic CRDC CSVs exercise the real extraction SQL (suppressed-total
handling, the high-school filter, all eight courses, and the support-staff fields), then the
full k12.parquet is run through build_k12 to check the site JSON (courses, staff, breadth).
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


def _race_cols(prefix, **over):
    d = {f"{prefix}_{r}_{s}": "0" for r in RACES for s in ("M", "F")}
    d.update(over)
    return d


def _course_file(folder, fname, offer_col, hs_offer, enr_prefix, hs_enr):
    hs = {"COMBOKEY": "HS1", offer_col: hs_offer, **_race_cols(enr_prefix, **hs_enr)}
    es = {"COMBOKEY": "ES1", offer_col: "0", **_race_cols(enr_prefix)}
    _write(folder / fname, [hs, es])


def _mk_crdc(folder):
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
    # 200 students, TOT_ENR_F suppressed but race cells present.
    _write(
        folder / "Enrollment.csv",
        [
            {
                "COMBOKEY": "HS1",
                **_race_cols("SCH_ENR", SCH_ENR_WH_M="100", SCH_ENR_BL_M="50", SCH_ENR_HI_M="50"),
                "TOT_ENR_M": "200",
                "TOT_ENR_F": "-11",
            },
            {"COMBOKEY": "ES1", **_race_cols("SCH_ENR", SCH_ENR_WH_M="300")},
        ],
    )
    _course_file(
        folder,
        "Advanced Placement.csv",
        "SCH_APENR_IND",
        "Yes",
        "SCH_APENR",
        {"SCH_APENR_WH_M": "40", "SCH_APCOURSES": "8"},
    )
    _course_file(
        folder,
        "Calculus.csv",
        "SCH_MATHCLASSES_CALC",
        "2",
        "SCH_MATHENR_CALC",
        {"SCH_MATHENR_CALC_WH_M": "20"},
    )
    _course_file(folder, "Physics.csv", "SCH_SCICLASSES_PHYS", "0", "SCH_SCIENR_PHYS", {})
    _course_file(
        folder,
        "Chemistry.csv",
        "SCH_SCICLASSES_CHEM",
        "1",
        "SCH_SCIENR_CHEM",
        {"SCH_SCIENR_CHEM_WH_M": "30"},
    )
    _course_file(
        folder,
        "Computer Science.csv",
        "SCH_COMPCLASSES_CSCI",
        "2",
        "SCH_COMPENR_CSCI",
        {"SCH_COMPENR_CSCI_WH_M": "15"},
    )
    _course_file(
        folder,
        "Dual Enrollment.csv",
        "SCH_DUAL_IND",
        "Yes",
        "SCH_DUALENR",
        {"SCH_DUALENR_WH_M": "25"},
    )
    _course_file(folder, "International Baccalaureate.csv", "SCH_IBENR_IND", "No", "SCH_IBENR", {})
    _course_file(
        folder,
        "Gifted and Talented.csv",
        "SCH_GT_IND",
        "Yes",
        "SCH_GTENR",
        {"SCH_GTENR_WH_M": "18"},
    )
    _write(
        folder / "School Support.csv",
        [
            {
                "COMBOKEY": "HS1",
                "SCH_FTECOUNSELORS": "2",
                "SCH_FTESECURITY_LEO": "1",
                "SCH_FTESECURITY_GUA": "0",
                "SCH_FTETEACH_TOT": "10",
                "SCH_FTETEACH_NOTCERT": "1",
            },
            {
                "COMBOKEY": "ES1",
                "SCH_FTECOUNSELORS": "1",
                "SCH_FTESECURITY_LEO": "0",
                "SCH_FTESECURITY_GUA": "0",
                "SCH_FTETEACH_TOT": "20",
                "SCH_FTETEACH_NOTCERT": "0",
            },
        ],
    )


def _build_k12_table(folder):
    con = duckdb.connect()
    bks.build(con, folder)
    return con


def test_source_extracts_courses_and_staff(tmp_path):
    _mk_crdc(tmp_path)
    con = _build_k12_table(tmp_path)
    rows = con.execute("SELECT * FROM k12").fetchdf().to_dict("records")
    assert len(rows) == 1  # elementary excluded
    hs = rows[0]
    assert hs["enroll_total"] == 200  # from race cells, not the suppressed total
    assert hs["offers_ap"] and hs["ap_courses"] == 8 and hs["ap_enroll"] == 40
    assert hs["offers_calc"] and not hs["offers_physics"]
    assert hs["offers_chem"] and hs["offers_cs"] and hs["offers_dual"] and hs["offers_gt"]
    assert not hs["offers_ib"]
    assert hs["fte_counselors"] == 2 and hs["fte_police"] == 1 and hs["fte_guards"] == 0
    assert hs["fte_teachers"] == 10 and hs["fte_teach_uncert"] == 1


def test_build_k12_site(tmp_path, monkeypatch):
    _mk_crdc(tmp_path)
    pq = tmp_path / "parquet"
    pq.mkdir()
    con = _build_k12_table(tmp_path)
    con.execute(f"COPY k12 TO '{pq / 'k12.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bk, "PARQUET_DIR", pq)
    monkeypatch.setattr(bk, "OUT_DIR", tmp_path / "k12-data")
    bk.main()

    s = json.loads((tmp_path / "k12-data" / "schools" / "TX.json").read_text())["HS1"]
    assert s["breadth3"] == 2  # AP + calculus, not physics
    assert s["courses"]["ap"]["rate"] == 20 and s["courses"]["ap"]["courses"] == 8
    assert s["courses"]["cs"]["offered"] and not s["courses"]["ib"]["offered"]
    assert s["staff"]["counselor_ratio"] == 100  # 200 students / 2 counselors
    assert s["staff"]["police"] is True and s["staff"]["guard"] is False
    assert s["staff"]["uncert_pct"] == 10  # 1 of 10 teachers
    idx = json.loads((tmp_path / "k12-data" / "index.json").read_text())
    assert idx["vintage"] == "2020-21" and idx["schools"][0]["k"] == "HS1"
