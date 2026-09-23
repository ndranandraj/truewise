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
                "JJ": "No",
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
                "JJ": "No",
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
    assert idx["vintage"] == "2021-22" and idx["schools"][0]["k"] == "HS1"


def test_negative_crdc_codes_are_unknown_not_no(tmp_path, monkeypatch):
    """CRDC marks non-response with negative sentinels (-9 "did not report"). Those must become
    NULL (unknown), never FALSE, so a school that did not report AP is not published as "does not
    offer AP". This is the same missingness bug class as the 0%-completion sentinel, and it moved
    a published K-12 headline before it was caught."""
    _mk_crdc(tmp_path)
    # AP indicator and the Calculus class-count are non-response (-9); physics stays an observed 0,
    # which is a real "offers none".
    _course_file(
        tmp_path,
        "Advanced Placement.csv",
        "SCH_APENR_IND",
        "-9",
        "SCH_APENR",
        {"SCH_APCOURSES": "-9"},
    )
    _course_file(tmp_path, "Calculus.csv", "SCH_MATHCLASSES_CALC", "-9", "SCH_MATHENR_CALC", {})
    _course_file(tmp_path, "Physics.csv", "SCH_SCICLASSES_PHYS", "0", "SCH_SCIENR_PHYS", {})
    con = _build_k12_table(tmp_path)
    ap, calc, phys = con.execute(
        "SELECT offers_ap, offers_calc, offers_physics FROM k12"
    ).fetchone()
    assert ap is None, "unreported AP indicator (-9) must be NULL, not False"
    assert calc is None, "negative class-count sentinel (-9) must be NULL, not False"
    assert phys is False, "an observed 0 classes is a real 'offers none'"

    pq = tmp_path / "parquet"
    pq.mkdir()
    con.execute(f"COPY k12 TO '{pq / 'k12.parquet'}' (FORMAT PARQUET)")
    monkeypatch.setattr(bk, "PARQUET_DIR", pq)
    monkeypatch.setattr(bk, "OUT_DIR", tmp_path / "k12-data")
    bk.main()
    s = json.loads((tmp_path / "k12-data" / "schools" / "TX.json").read_text())["HS1"]
    assert s["courses"]["ap"]["offered"] is None, "AP must render as 'not reported', not offered"
    assert s["courses"]["calc"]["offered"] is None
    assert s["courses"]["phys"]["offered"] is False
    assert s["breadth3"] == 0  # nothing KNOWN offered among the three (unknowns are not counted)
    idx = json.loads((tmp_path / "k12-data" / "index.json").read_text())["schools"][0]
    assert idx["ap"] is None and idx["c"] is None and idx["p"] is False


def test_race_sums_include_the_nonbinary_column_when_published():
    """2021-22 reports 10,810 students in SCH_ENR_*_X; summing only _M and _F left them out."""
    from pipeline.build_k12_source import _sum_races

    without = _sum_races("e", "SCH_ENR", races=("WH",))
    assert "SCH_ENR_WH_X" not in without
    present = frozenset({"SCH_ENR_WH_M", "SCH_ENR_WH_F", "SCH_ENR_WH_X"})
    assert "e.SCH_ENR_WH_X" in _sum_races("e", "SCH_ENR", races=("WH",), present=present)


def test_a_release_without_any_no_is_refused(monkeypatch):
    """2023-24 publishes a high school's AP "No" as -9. Built naively, every such school would read
    "not reported" and the AP offer rate would be computed over offering schools only."""
    import duckdb
    import pytest

    from pipeline import build_k12_source as b
    from pipeline.build_k12_source import _check_indicator_vocabulary

    monkeypatch.setattr(b, "MIN_HS_FOR_VOCAB_CHECK", 1)

    con = duckdb.connect()
    con.execute(
        "CREATE VIEW chars AS SELECT * FROM (VALUES ('1','Yes','No','No','No'),('2','Yes','No','No','No')) "
        "t(COMBOKEY, SCH_GRADE_G09, SCH_GRADE_G10, SCH_GRADE_G11, SCH_GRADE_G12)"
    )
    for view, col in (("ap", "SCH_APENR_IND"), ("ib", "SCH_IBENR_IND"), ("dual", "SCH_DUAL_IND")):
        con.execute(
            f"CREATE VIEW {view} AS SELECT * FROM (VALUES ('1','Yes'),('2','No')) t(COMBOKEY, {col})"
        )
    _check_indicator_vocabulary(con)
    con.execute(
        "CREATE OR REPLACE VIEW ap AS SELECT * FROM (VALUES ('1','Yes'),('2','-9')) t(COMBOKEY, SCH_APENR_IND)"
    )
    with pytest.raises(SystemExit, match="SCH_APENR_IND"):
        _check_indicator_vocabulary(con)


def _as_2023_24(folder, justice="No", ap_courses="-9"):
    """Rewrite the fixture in the 2023-24 layout, where AP and IB "No" is published as -9."""
    path = folder / "School Characteristics.csv"
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        r.pop("JJ")
        r["SCH_JUST_IND"] = justice
    _write(path, rows)
    _course_file(
        folder,
        "Advanced Placement.csv",
        "SCH_APENR_IND",
        "-9",
        "SCH_APENR",
        {"SCH_APCOURSES": ap_courses},
    )
    _course_file(folder, "International Baccalaureate.csv", "SCH_IBENR_IND", "-9", "SCH_IBENR", {})


def test_2023_24_reads_minus9_as_no_at_a_regular_high_school(tmp_path):
    """ED's form asks every high school AP and IB as required Yes/No; 2023-24 publishes "No" as -9."""
    _mk_crdc(tmp_path)
    _as_2023_24(tmp_path)
    hs = _build_k12_table(tmp_path).execute("SELECT * FROM k12").fetchdf().to_dict("records")[0]
    assert hs["crdc_vintage"] == "2023-24"
    assert hs["offers_ap"] is False and hs["offers_ib"] is False


def test_2023_24_minus9_stays_unknown_where_a_skip_is_plausible(tmp_path):
    _mk_crdc(tmp_path)
    _as_2023_24(tmp_path, justice="Yes")
    hs = _build_k12_table(tmp_path).execute("SELECT * FROM k12").fetchdf().to_dict("records")[0]
    assert hs["offers_ap"] is None and hs["offers_ib"] is None, "a justice facility's -9 is unknown"

    _mk_crdc(tmp_path)
    _as_2023_24(tmp_path, ap_courses="3")
    hs = _build_k12_table(tmp_path).execute("SELECT * FROM k12").fetchdf().to_dict("records")[0]
    assert hs["offers_ap"] is None, "a -9 indicator beside a real course count is inconsistent"


def test_crdc_labels_follow_the_published_data():
    """Every page that names the CRDC collection names the one published/k12.parquet was built from."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    con = duckdb.connect()
    (vintage,) = con.execute(
        f"SELECT DISTINCT crdc_vintage FROM read_parquet('{root / 'published' / 'k12.parquet'}')"
    ).fetchone()
    pages = [
        "site/index.html",
        "site/methodology/index.html",
        "site/k12/index.html",
        "site/k12/rankings/index.html",
        "site/k12/advanced-courses/index.html",
        "README.md",
    ]
    for page in pages:
        text = (root / page).read_text()
        named = set(
            re.findall(r"(?:CRDC|Civil Rights Data Collection)[^.<]{0,12}?(20\d\d-\d\d)", text)
        )
        named |= set(re.findall(r"<b>(20\d\d-\d\d)</b> (?:CRDC|collection)", text))
        named |= set(re.findall(r"(20\d\d-\d\d)\s+federal collection", text))
        assert named, f"{page} should name the CRDC collection"
        assert named == {vintage}, f"{page} names {named}, the data is {vintage}"
