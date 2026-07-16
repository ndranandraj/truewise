"""Tests for the Careers field aggregation and the BLS demand transform.

Both run without any download: the field builder reads a synthetic value_check parquet, and
the demand transform runs on synthetic xwalk/oews/ep tables, exercising the exact SQL that ships.
"""

from __future__ import annotations

import json

import duckdb

import pipeline.build_careers as bc
import pipeline.build_careers_demand as bcd


def test_build_careers_aggregates_fields(tmp_path, monkeypatch):
    pq = tmp_path / "parquet"
    pq.mkdir()
    out = tmp_path / "careers-data"
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE vc(unitid VARCHAR, cip_code VARCHAR, cip_desc VARCHAR, "
        "credential_level VARCHAR, credential_desc VARCHAR, earnings DOUBLE, value_flag VARCHAR)"
    )
    rows = []
    for i in range(6):  # 6 nursing BA programs at 6 schools; 5 pass, 1 fails
        flag = "fails_earnings_premium" if i == 0 else "passes_earnings_premium"
        rows.append(
            (
                str(100 + i),
                "5138",
                "Registered Nursing.",
                "3",
                "Bachelor's Degree",
                60000.0 + i * 1000,
                flag,
            )
        )
    rows.append(
        ("200", "5138", "Registered Nursing.", "3", "Bachelor's Degree", None, "insufficient_data")
    )
    con.executemany("INSERT INTO vc VALUES (?,?,?,?,?,?,?)", rows)
    con.execute(f"COPY vc TO '{pq / 'value_check.parquet'}' (FORMAT PARQUET)")

    monkeypatch.setattr(bc, "PARQUET_DIR", pq)
    monkeypatch.setattr(bc, "OUT_DIR", out)
    bc.main()

    fields = json.loads((out / "fields.json").read_text())["fields"]
    f = next(x for x in fields if x["cip"] == "5138")
    assert f["credential"] == "Bachelor's Degree"
    assert f["family"] == "Health Professions"
    assert f["programs"] == 6 and f["schools"] == 6  # insufficient/suppressed row excluded
    assert f["pass_pct"] == 83  # 5 of 6
    assert f["p25"] is not None and f["p75"] is not None and f["med"] is not None


def test_build_demand_lists_occupations_with_outlook():
    con = duckdb.connect()
    con.execute("CREATE TABLE xwalk(cip VARCHAR, soc VARCHAR)")
    con.executemany("INSERT INTO xwalk VALUES (?,?)", [("5138", "29-1141"), ("1101", "15-1252")])
    con.execute("CREATE TABLE oews(soc VARCHAR, title VARCHAR, wage DOUBLE)")
    con.executemany(
        "INSERT INTO oews VALUES (?,?,?)",
        [("29-1141", "Registered Nurses", 81000.0), ("15-1252", "Software Developers", 132000.0)],
    )
    con.execute("CREATE TABLE ep(soc VARCHAR, growth DOUBLE, openings DOUBLE)")
    con.executemany(
        "INSERT INTO ep VALUES (?,?,?)",
        [("29-1141", 6.0, 193100.0), ("15-1252", 17.0, 153900.0)],
    )
    bcd.build_demand(con)

    d = dict(con.execute("SELECT cip_code, demand_json FROM careers_demand").fetchall())
    assert set(d) == {"5138", "1101"}
    nursing = json.loads(d["5138"])
    assert nursing["annual_openings"] == 193100
    assert nursing["growth_pct"] == 6
    assert nursing["occupations"][0]["title"] == "Registered Nurses"
    assert nursing["occupations"][0]["wage"] == 81000
