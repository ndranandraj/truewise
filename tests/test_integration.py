"""End-to-end integration test: fixture CSVs → spine → value_check → site JSON.

Exercises resolve_columns, the institution-threshold join, the flag SQL, and the JSON
site generator together, on a handful of synthetic programs. No network, no real data.
"""

from __future__ import annotations

import json

import duckdb
import pytest

import pipeline.build_site as bsite
import pipeline.build_spine as bs
import pipeline.value_check as vc

FOS_CSV = """UNITID,OPEID6,INSTNM,CONTROL,CIPCODE,CIPDESC,CREDLEV,CREDDESC,IPEDSCOUNT1,EARN_MDN_1YR,EARN_MDN_4YR,DEBT_ALL_STGP_EVAL_MDN
100,001000,Test State University,Public,0101,Computer Science.,3,Bachelor's Degree,120,40000,60000,20000
100,001000,Test State University,Public,0202,Poetry.,3,Bachelor's Degree,55,18000,25000,24000
100,001000,Test State University,Public,0303,Tiny Program.,3,Bachelor's Degree,8,PS,PS,PS
999,009990,National Aggregate,Public,0101,Computer Science.,3,Bachelor's Degree,0,50000,70000,10000
"""

INST_CSV = """UNITID,INSTNM,CITY,STABBR,INSTURL,UGDS,EARN_THR_STATE,EARN_THR_NAT,NPT4_PUB,NPT41_PUB,NPT42_PUB,NPT43_PUB,NPT44_PUB,NPT45_PUB
100,Test State University,Testville,TX,tsu.edu,12000,35000,36000,15000,6000,9000,13000,17000,21000
"""


@pytest.fixture
def built(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "Most-Recent-Cohorts-Field-of-Study.csv").write_text(FOS_CSV)
    (raw / "Most-Recent-Cohorts-Institution.csv").write_text(INST_CSV)
    pq = tmp_path / "parquet"
    db = tmp_path / "tw.duckdb"
    arch = tmp_path / "archive"

    for mod in (bs, vc):
        monkeypatch.setattr(mod, "DB_PATH", db, raising=False)
        monkeypatch.setattr(mod, "PARQUET_DIR", pq, raising=False)
    monkeypatch.setattr(bs, "RAW_DIR", raw)
    monkeypatch.setattr(vc, "ARCHIVE_DIR", arch)

    bs.main()
    vc.main()
    return {"pq": pq, "tmp": tmp_path}


def test_flags_end_to_end(built):
    con = duckdb.connect()
    rows = dict(
        con.execute(
            f"SELECT cip_code, value_flag FROM read_parquet('{built['pq']}/value_check.parquet') "
            "WHERE unitid='100'"
        ).fetchall()
    )
    assert rows["0101"] == "passes_earnings_premium"  # 60k (4yr) > 35k threshold
    assert rows["0202"] == "fails_earnings_premium"  # 25k < 35k
    assert rows["0303"] == "insufficient_data"  # earnings suppressed


def test_earnings_uses_4yr(built):
    con = duckdb.connect()
    earn, horizon = con.execute(
        f"SELECT earnings, earnings_horizon FROM read_parquet('{built['pq']}/value_check.parquet') "
        "WHERE unitid='100' AND cip_code='0101'"
    ).fetchone()
    assert earn == 60000
    assert horizon == "4yr_after_completion"


def test_site_generator(built, tmp_path, monkeypatch):
    out = tmp_path / "site-data"
    monkeypatch.setattr(bsite, "PARQUET_DIR", built["pq"])
    monkeypatch.setattr(bsite, "OUT_DIR", out)
    bsite.main()

    schools = json.loads((out / "schools.json").read_text())["schools"]
    tsu = next(s for s in schools if s["unitid"] == "100")
    assert tsu["n_fail"] == 1 and tsu["n_pass"] == 1 and tsu["n_insufficient"] == 1
    assert tsu["state"] == "TX"
    # identity + affordability flow through
    assert tsu["city"] == "Testville" and tsu["enrollment"] == 12000
    assert tsu["net_price"]["avg"] == 15000
    assert tsu["net_price"]["brackets"] == [6000, 9000, 13000, 17000, 21000]

    tx = json.loads((out / "programs" / "TX.json").read_text())
    progs = {p["cip"]: p for p in tx["100"]}
    assert progs["0101"]["flag"] == "passes_earnings_premium"
    assert progs["0101"]["earnings"] == 60000
    # insufficient-data programs are excluded from the shards (index still counts them)
    assert "0303" not in progs
